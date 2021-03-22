#include "logger.h"
#include "dbconnector.h"
#include "producerstatetable.h"
#include "tokenize.h"
#include "ipprefix.h"
#include "portmgr.h"
#include "exec.h"
#include "shellcmd.h"

using namespace std;
using namespace swss;

#define ETHERNET_PREFIX "Ethernet"

PortMgr::PortMgr(DBConnector *cfgDb, DBConnector *appDb, DBConnector *stateDb, const vector<string> &tableNames) :
        Orch(cfgDb, tableNames),
        m_cfgPortTable(cfgDb, CFG_PORT_TABLE_NAME),
        m_cfgLagMemberTable(cfgDb, CFG_LAG_MEMBER_TABLE_NAME),
        m_statePortTable(stateDb, STATE_PORT_TABLE_NAME),
        m_appPortTable(appDb, APP_PORT_TABLE_NAME)
{
}

bool PortMgr::setPortMtu(const string &alias, const string &mtu)
{
    stringstream cmd;
    string res;

    // ip link set dev <port_name> mtu <mtu>
    cmd << IP_CMD << " link set dev " << shellquote(alias) << " mtu " << shellquote(mtu);
    EXEC_WITH_ERROR_THROW(cmd.str(), res);

    // Set the port MTU in application database to update both
    // the port MTU and possibly the port based router interface MTU
    vector<FieldValueTuple> fvs;
    FieldValueTuple fv("mtu", mtu);
    fvs.push_back(fv);
    m_appPortTable.set(alias, fvs);

    return true;
}

bool PortMgr::setSubPortMtu(const string &alias, const string &mtu)
{
    SWSS_LOG_ENTER();

    stringstream cmd;
    string res;

    // ip link set <sub_port_name> mtu <mtu>
    cmd << IP_CMD << " link set " << shellquote(alias) << " mtu " << shellquote(mtu);
    EXEC_WITH_ERROR_THROW(cmd.str(), res);

    return true;
}

bool PortMgr::setPortAdminStatus(const string &alias, const bool up)
{
    stringstream cmd;
    string res;

    // ip link set dev <port_name> [up|down]
    cmd << IP_CMD << " link set dev " << shellquote(alias) << (up ? " up" : " down");
    EXEC_WITH_ERROR_THROW(cmd.str(), res);

    vector<FieldValueTuple> fvs;
    FieldValueTuple fv("admin_status", (up ? "up" : "down"));
    fvs.push_back(fv);
    m_appPortTable.set(alias, fvs);

    return true;
}

bool PortMgr::setSubPortAdminStatus(const string &alias, const bool up)
{
    stringstream cmd;
    string res;

    // ip link set <sub_port_name> [up|down]
    cmd << IP_CMD << " link set " << shellquote(alias) << (up ? " up" : " down");
    EXEC_WITH_ERROR_THROW(cmd.str(), res);

    return true;
}

bool PortMgr::setPortLearnMode(const string &alias, const string &learn_mode)
{
    // Set the port MAC learn mode in application database
    vector<FieldValueTuple> fvs;
    FieldValueTuple fv("learn_mode", learn_mode);
    fvs.push_back(fv);
    m_appPortTable.set(alias, fvs);

    return true;
}

void PortMgr::setSubPortStateOk(const string &alias)
{
    vector<FieldValueTuple> fvTuples = {{"state", "ok"}};

    m_statePortTable.set(alias, fvTuples);
}

bool PortMgr::isPortStateOk(const string &alias)
{
    vector<FieldValueTuple> temp;

    if (m_statePortTable.get(alias, temp))
    {
        SWSS_LOG_INFO("Port %s is ready", alias.c_str());
        return true;
    }

    return false;
}

void PortMgr::removeSubPortState(const string &alias)
{
    m_statePortTable.del(alias);
}

void PortMgr::addHostSubPort(const string &port, const string &subPort, const string &vlan)
{
    stringstream cmd;
    string res;

    cmd << IP_CMD " link add link " << shellquote(port) << " name " << shellquote(subPort) << " type vlan id " << shellquote(vlan);
    EXEC_WITH_ERROR_THROW(cmd.str(), res);
}

void PortMgr::removeHostSubPort(const string &subPort)
{
    stringstream cmd;
    string res;

    cmd << IP_CMD " link del " << shellquote(subPort);
    EXEC_WITH_ERROR_THROW(cmd.str(), res);
}

void PortMgr::doTask(Consumer &consumer)
{
    SWSS_LOG_ENTER();

    auto table = consumer.getTableName();

    if (table == CFG_PORT_TABLE_NAME)
    {
        doPortTask(consumer);
    }
    else if (table == CFG_VLAN_SUB_INTF_TABLE_NAME)
    {
        doSubPortTask(consumer);
    }
}

void PortMgr::doPortTask(Consumer &consumer)
{
    SWSS_LOG_ENTER();

    auto it = consumer.m_toSync.begin();
    while (it != consumer.m_toSync.end())
    {
        KeyOpFieldsValuesTuple t = it->second;

        string alias = kfvKey(t);
        string op = kfvOp(t);

        if (op == SET_COMMAND)
        {
            if (!isPortStateOk(alias))
            {
                SWSS_LOG_INFO("Port %s is not ready, pending...", alias.c_str());
                it++;
                continue;
            }

            string admin_status, mtu, learn_mode;

            bool configured = (m_portList.find(alias) != m_portList.end());

            /* If this is the first time we set port settings
             * assign default admin status and mtu
             */
            if (!configured)
            {
                admin_status = DEFAULT_ADMIN_STATUS_STR;
                mtu = DEFAULT_MTU_STR;

                m_portList.insert(alias);
            }

            for (auto i : kfvFieldsValues(t))
            {
                if (fvField(i) == "mtu")
                {
                    mtu = fvValue(i);
                }
                else if (fvField(i) == "admin_status")
                {
                    admin_status = fvValue(i);
                }
                else if (fvField(i) == "learn_mode")
                {
                    learn_mode = fvValue(i);
                }
            }

            if (!mtu.empty())
            {
                setPortMtu(alias, mtu);
                SWSS_LOG_NOTICE("Configure %s MTU to %s", alias.c_str(), mtu.c_str());

                for (const auto &subPort : m_portSubPortSet[alias])
                {
                    if (m_subPortCfgMap[subPort].mtu.empty())
                    {
                        try
                        {
                            setSubPortMtu(subPort, mtu);
                            SWSS_LOG_NOTICE("Configure sub port %s MTU to %s, inherited from parent port %s",
                                            subPort.c_str(), mtu.c_str(), alias.c_str());
                        }
                        catch (const std::runtime_error &e)
                        {
                            SWSS_LOG_NOTICE("Sub port ip link set mtu failure. Runtime error: %s", e.what());
                        }
                    }
                }
            }

            if (!admin_status.empty())
            {
                setPortAdminStatus(alias, admin_status == "up");
                SWSS_LOG_NOTICE("Configure %s admin status to %s", alias.c_str(), admin_status.c_str());

                for (const auto &subPort : m_portSubPortSet[alias])
                {
                    const auto &subPortAdminStatus = m_subPortCfgMap[subPort].adminStatus;
                    try
                    {
                        setSubPortAdminStatus(subPort, subPortAdminStatus == "up");
                        SWSS_LOG_NOTICE("Configure sub port %s admin status to %s",
                                        subPort.c_str(), subPortAdminStatus.c_str());
                    }
                    catch (const std::runtime_error &e)
                    {
                        SWSS_LOG_NOTICE("Sub port ip link set admin status failure. Runtime error: %s", e.what());
                    }
                }
            }

            if (!learn_mode.empty())
            {
                setPortLearnMode(alias, learn_mode);
                SWSS_LOG_NOTICE("Configure %s MAC learn mode to %s", alias.c_str(), learn_mode.c_str());
            }
        }
        else if (op == DEL_COMMAND)
        {
            SWSS_LOG_NOTICE("Delete Port: %s", alias.c_str());
            m_appPortTable.del(alias);
            m_portList.erase(alias);
        }

        it = consumer.m_toSync.erase(it);
    }
}

void PortMgr::doSubPortTask(Consumer &consumer)
{
    SWSS_LOG_ENTER();

    auto it = consumer.m_toSync.begin();
    while (it != consumer.m_toSync.end())
    {
        KeyOpFieldsValuesTuple &t = it->second;
        vector<string> keys = tokenize(kfvKey(t), config_db_key_delimiter);
        string op = kfvOp(t);

        if (keys.size() == 1)
        {
            string alias(keys[0]);
            if (alias.compare(0, strlen(ETHERNET_PREFIX), ETHERNET_PREFIX))
            {
                it = consumer.m_toSync.erase(it);
                continue;
            }

            string parentAlias;
            string vlanId;
            size_t found = alias.find(VLAN_SUB_INTERFACE_SEPARATOR);
            if (found != string::npos)
            {
                vlanId = alias.substr(found + 1);
                parentAlias = alias.substr(0, found);
            }
            else
            {
                it = consumer.m_toSync.erase(it);
                continue;
            }

            if (op == SET_COMMAND)
            {
                if (!isPortStateOk(parentAlias))
                {
                    SWSS_LOG_INFO("Parent port %s is not ready, pending...", parentAlias.c_str());
                    it++;
                    continue;
                }

                if (m_subPortList.find(alias) == m_subPortList.end())
                {
                    try
                    {
                        addHostSubPort(parentAlias, alias, vlanId);
                    }
                    catch (const std::runtime_error &e)
                    {
                        SWSS_LOG_NOTICE("Sub interface ip link add failure. Runtime error: %s", e.what());
                        it++;
                        continue;
                    }

                    m_subPortList.insert(alias);
                    m_portSubPortSet[parentAlias].insert(alias);
                }

                string mtu = "";
                string adminStatus = "up";
                const vector<FieldValueTuple> &fvTuples = kfvFieldsValues(t);
                for (const auto &fv : fvTuples)
                {
                    if (fvField(fv) == "mtu")
                    {
                        mtu = fvValue(fv);
                    }
                    else if (fvField(fv) == "admin_status")
                    {
                        adminStatus = fvValue(fv);
                    }
                }

                if (!mtu.empty())
                {
                    try
                    {
                        setSubPortMtu(alias, mtu);
                        SWSS_LOG_NOTICE("Configure sub port %s MTU to %s, inherited from parent port %s",
                                        alias.c_str(), mtu.c_str(), parentAlias.c_str());
                    }
                    catch (const std::runtime_error &e)
                    {
                        SWSS_LOG_NOTICE("Sub port ip link set mtu failure. Runtime error: %s", e.what());
                        it++;
                        continue;
                    }
                }

                try
                {
                    setSubPortAdminStatus(alias, adminStatus == "up");
                }
                catch (const std::runtime_error &e)
                {
                    SWSS_LOG_NOTICE("Sub port ip link set admin status %s failure. Runtime error: %s", adminStatus.c_str(), e.what());
                    it++;
                    continue;
                }

                m_subPortCfgMap[alias].mtu = mtu;
                m_subPortCfgMap[alias].adminStatus = adminStatus;
                // set STATE_DB port state
                setSubPortStateOk(alias);
            }
            else if (op == DEL_COMMAND)
            {
                removeHostSubPort(alias);
                m_subPortList.erase(alias);
                m_portSubPortSet[parentAlias].erase(alias);
                m_subPortCfgMap.erase(alias);

                removeSubPortState(alias);
            }
        }

        it = consumer.m_toSync.erase(it);
    }
}
