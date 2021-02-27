#pragma once

#include "dbconnector.h"
#include "orch.h"
#include "producerstatetable.h"

#include <map>
#include <set>
#include <string>

namespace swss {

/* Port default admin status is down */
#define DEFAULT_ADMIN_STATUS_STR    "down"
#define DEFAULT_MTU_STR             "9100"

class PortMgr : public Orch
{
public:
    PortMgr(DBConnector *cfgDb, DBConnector *appDb, DBConnector *stateDb, const std::vector<std::string> &tableNames);

    using Orch::doTask;
private:
    Table m_cfgPortTable;
    Table m_cfgLagMemberTable;
    Table m_statePortTable;
    ProducerStateTable m_appPortTable;

    std::set<std::string> m_portList;
    std::unordered_map<std::string, std::unordered_set<std::string>> m_portSubPortSet;

    void doTask(Consumer &consumer);
    void doPortTask(Consumer &consumer);
    void doSubPortTask(Consumer &consumer);
    bool setPortMtu(const std::string &alias, const std::string &mtu);
    bool setSubPortMtu(const std::string &alias, const std::string &mtu);
    bool setPortAdminStatus(const std::string &alias, const bool up);
    bool setPortLearnMode(const std::string &alias, const std::string &learn_mode);
    bool isPortStateOk(const std::string &alias);
};

}
