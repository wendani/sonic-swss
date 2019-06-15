#include <string>
#include <netinet/in.h>
#include <netlink/route/link.h>
#include <netlink/route/neighbour.h>

#include "logger.h"
#include "dbconnector.h"
#include "producerstatetable.h"
#include "ipaddress.h"
#include "netmsg.h"
#include "linkcache.h"
#include "macaddress.h"

#include "neighsync.h"
#include "warm_restart.h"

using namespace std;
using namespace swss;

NeighSync::NeighSync(RedisPipeline *pipelineAppDB, DBConnector *stateDb) :
    m_neighTable(pipelineAppDB, APP_NEIGH_TABLE_NAME),
    m_stateNeighRestoreTable(stateDb, STATE_NEIGH_RESTORE_TABLE_NAME),
    m_AppRestartAssist(pipelineAppDB, "neighsyncd", "swss", &m_neighTable, DEFAULT_NEIGHSYNC_WARMSTART_TIMER)
{
}

// Check if neighbor table is restored in kernel
bool NeighSync::isNeighRestoreDone()
{
    string value;

    m_stateNeighRestoreTable.hget("Flags", "restored", value);
    if (value == "true")
    {
        SWSS_LOG_NOTICE("neighbor table restore to kernel is done");
        return true;
    }
    return false;
}

void NeighSync::onMsg(int nlmsg_type, struct nl_object *obj)
{
    char ipStr[MAX_ADDR_SIZE + 1] = {0};
    char macStr[MAX_ADDR_SIZE + 1] = {0};
    struct rtnl_neigh *neigh = (struct rtnl_neigh *)obj;
    string key;
    string family;

    if ((nlmsg_type != RTM_NEWNEIGH) && (nlmsg_type != RTM_GETNEIGH) &&
        (nlmsg_type != RTM_DELNEIGH))
        return;

    if (rtnl_neigh_get_family(neigh) == AF_INET)
        family = IPV4_NAME;
    else if (rtnl_neigh_get_family(neigh) == AF_INET6)
        family = IPV6_NAME;
    else
        return;

    key+= LinkCache::getInstance().ifindexToName(rtnl_neigh_get_ifindex(neigh));
    key+= ":";

    nl_addr2str(rtnl_neigh_get_dst(neigh), ipStr, MAX_ADDR_SIZE);
    /* Ignore IPv6 link-local addresses as neighbors */
    if (family == IPV6_NAME && IN6_IS_ADDR_LINKLOCAL(nl_addr_get_binary_addr(rtnl_neigh_get_dst(neigh))))
        return;
    /* Ignore IPv6 multicast link-local addresses as neighbors */
    if (family == IPV6_NAME && IN6_IS_ADDR_MC_LINKLOCAL(nl_addr_get_binary_addr(rtnl_neigh_get_dst(neigh))))
        return;
    key+= ipStr;

    int state = rtnl_neigh_get_state(neigh);
    bool delete_key = false;
    if ((nlmsg_type == RTM_DELNEIGH) || (state == NUD_INCOMPLETE) ||
        (state == NUD_FAILED))
    {
	    delete_key = true;
    }

    nl_addr2str(rtnl_neigh_get_lladdr(neigh), macStr, MAX_ADDR_SIZE);

    /* Ignore neighbor entries with Broadcast Mac - Trigger for directed broadcast */
    if (!delete_key && (MacAddress(macStr) == MacAddress("ff:ff:ff:ff:ff:ff")))
    {
        SWSS_LOG_INFO("Broadcast Mac recieved, ignoring for %s", ipStr);
        return;
    }

    std::vector<FieldValueTuple> fvVector;
    FieldValueTuple f("family", family);
    FieldValueTuple nh("neigh", macStr);
    fvVector.push_back(nh);
    fvVector.push_back(f);

    // If warmstart is in progress, we take all netlink changes into the cache map
    if (m_AppRestartAssist.isWarmStartInProgress())
    {
        m_AppRestartAssist.insertToMap(key, fvVector, delete_key);
    }
    else
    {
        if (delete_key == true)
        {
            m_neighTable.del(key);
            return;
        }
        m_neighTable.set(key, fvVector);
    }
}
