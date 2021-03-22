#ifndef __INTFMGR__
#define __INTFMGR__

#include "dbconnector.h"
#include "producerstatetable.h"
#include "orch.h"

#include <map>
#include <string>
#include <set>

namespace swss {

class IntfMgr : public Orch
{
public:
    IntfMgr(DBConnector *cfgDb, DBConnector *appDb, DBConnector *stateDb, const std::vector<std::string> &tableNames);
    using Orch::doTask;

private:
    ProducerStateTable m_appIntfTableProducer;
    Table m_cfgIntfTable, m_cfgVlanIntfTable, m_cfgLagIntfTable, m_cfgLoopbackIntfTable;
    Table m_statePortTable, m_stateLagTable, m_stateVlanTable, m_stateVrfTable, m_stateIntfTable;

    std::set<std::string> m_loopbackIntfList;
    std::set<std::string> m_pendingReplayIntfList;

    void setIntfIp(const std::string &alias, const std::string &opCmd, const IpPrefix &ipPrefix);
    void setIntfVrf(const std::string &alias, const std::string &vrfName);
    void setIntfMac(const std::string &alias, const std::string &macAddr);

    bool doIntfGeneralTask(const std::vector<std::string>& keys, std::vector<FieldValueTuple> data, const std::string& op);
    bool doIntfAddrTask(const std::vector<std::string>& keys, const std::vector<FieldValueTuple>& data, const std::string& op);
    void doTask(Consumer &consumer);

    bool isIntfStateOk(const std::string &alias);
    bool isIntfCreated(const std::string &alias);
    bool isIntfChangeVrf(const std::string &alias, const std::string &vrfName);
    int getIntfIpCount(const std::string &alias);
    void buildIntfReplayList(void);

    void addLoopbackIntf(const std::string &alias);
    void delLoopbackIntf(const std::string &alias);
    void flushLoopbackIntfs(void);

    bool setIntfProxyArp(const std::string &alias, const std::string &proxy_arp);
    bool setIntfGratArp(const std::string &alias, const std::string &grat_arp);
};

}

#endif
