#ifndef __INTFMGR__
#define __INTFMGR__

#include "dbconnector.h"
#include "producerstatetable.h"
#include "orch.h"

#include <map>
#include <string>

namespace swss {

class IntfMgr : public Orch
{
public:
    IntfMgr(DBConnector *cfgDb, DBConnector *appDb, DBConnector *stateDb, const vector<string> &tableNames);
    using Orch::doTask;

private:
    ProducerStateTable m_appIntfTableProducer;
    Table m_statePortTable, m_stateLagTable, m_stateVlanTable, m_stateVrfTable, m_stateIntfTable;

    set<string> m_subIntfList;

    void setIntfIp(const string &alias, const string &opCmd, const IpPrefix &ipPrefix);
    void setIntfVrf(const string &alias, const string vrfName);
    bool doIntfGeneralTask(const vector<string>& keys, const vector<FieldValueTuple>& data, const string& op);
    bool doIntfAddrTask(const vector<string>& keys, const vector<FieldValueTuple>& data, const string& op);
    void doTask(Consumer &consumer);
    bool isIntfStateOk(const string &alias);

    void addHostSubIntf(const string&intf, const string &subIntf, const string &vlan);
    void setHostSubIntfMtu(const string &subIntf, const uint32_t mtu);
    void setHostSubIntfAdminStatus(const string &subIntf, const string &admin_status);
    void removeHostSubIntf(const string &subIntf);
    void setSubIntfStateOk(const string &alias);
    void removeSubIntfState(const string &alias);
};

}

#endif
