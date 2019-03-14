#include <limits.h>
#include <unordered_map>
#include "pfcwdorch.h"
#include "sai_serialize.h"
#include "portsorch.h"
#include "converter.h"
#include "redisapi.h"
#include "select.h"
#include "notifier.h"
#include "redisclient.h"
#include "schema.h"
#include "subscriberstatetable.h"

#define PFC_WD_GLOBAL                   "GLOBAL"
#define PFC_WD_ACTION                   "action"
#define PFC_WD_DETECTION_TIME           "detection_time"
#define PFC_WD_RESTORATION_TIME         "restoration_time"
#define BIG_RED_SWITCH_FIELD            "BIG_RED_SWITCH"
#define PFC_WD_IN_STORM                 "storm"

#define PFC_WD_DETECTION_TIME_MAX       (5 * 1000)
#define PFC_WD_DETECTION_TIME_MIN       100
#define PFC_WD_RESTORATION_TIME_MAX     (60 * 1000)
#define PFC_WD_RESTORATION_TIME_MIN     100
#define PFC_WD_POLL_TIMEOUT             5000
#define SAI_PORT_STAT_PFC_PREFIX        "SAI_PORT_STAT_PFC_"
#define PFC_WD_TC_MAX 8
#define COUNTER_CHECK_POLL_TIMEOUT_SEC  1

extern sai_port_api_t *sai_port_api;
extern sai_queue_api_t *sai_queue_api;

extern PortsOrch *gPortsOrch;

template <typename DropHandler, typename ForwardHandler>
PfcWdOrch<DropHandler, ForwardHandler>::PfcWdOrch(DBConnector *db, vector<string> &tableNames):
    Orch(db, tableNames),
    m_countersDb(new DBConnector(COUNTERS_DB, DBConnector::DEFAULT_UNIXSOCKET, 0)),
    m_countersTable(new Table(m_countersDb.get(), COUNTERS_TABLE))
{
    SWSS_LOG_ENTER();
}


template <typename DropHandler, typename ForwardHandler>
PfcWdOrch<DropHandler, ForwardHandler>::~PfcWdOrch(void)
{
    SWSS_LOG_ENTER();
}

template <typename DropHandler, typename ForwardHandler>
void PfcWdOrch<DropHandler, ForwardHandler>::doTask(Consumer& consumer)
{
    SWSS_LOG_ENTER();

    if (!gPortsOrch->isPortReady())
    {
        return;
    }

    if ((consumer.getDbId() == CONFIG_DB) && (consumer.getTableName() == CFG_PFC_WD_TABLE_NAME))
    {
        auto it = consumer.m_toSync.begin();
        while (it != consumer.m_toSync.end())
        {
            KeyOpFieldsValuesTuple t = it->second;

            string key = kfvKey(t);
            string op = kfvOp(t);

            if (op == SET_COMMAND)
            {
                createEntry(key, kfvFieldsValues(t));
            }
            else if (op == DEL_COMMAND)
            {
                deleteEntry(key);
            }
            else
            {
                SWSS_LOG_ERROR("Unknown operation type %s\n", op.c_str());
            }

            consumer.m_toSync.erase(it++);
        }

        if (consumer.m_toSync.empty())
        {
            m_entriesCreated = true;
            SWSS_LOG_NOTICE("PFC watchdog all entries created");
        }
    }
}

template <typename DropHandler, typename ForwardHandler>
template <typename T>
string PfcWdSwOrch<DropHandler, ForwardHandler>::counterIdsToStr(
        const vector<T> ids, string (*convert)(T))
{
    SWSS_LOG_ENTER();

    string str;

    for (const auto& i: ids)
    {
        str += convert(i) + ",";
    }

    // Remove trailing ','
    if (!str.empty())
    {
        str.pop_back();
    }

    return str;
}

template <typename DropHandler, typename ForwardHandler>
PfcWdAction PfcWdOrch<DropHandler, ForwardHandler>::deserializeAction(const string& key)
{
    SWSS_LOG_ENTER();

    const map<string, PfcWdAction> actionMap =
    {
        { "forward", PfcWdAction::PFC_WD_ACTION_FORWARD },
        { "drop", PfcWdAction::PFC_WD_ACTION_DROP },
        { "alert", PfcWdAction::PFC_WD_ACTION_ALERT },
    };

    if (actionMap.find(key) == actionMap.end())
    {
        return PfcWdAction::PFC_WD_ACTION_UNKNOWN;
    }

    return actionMap.at(key);
}

template <typename DropHandler, typename ForwardHandler>
string PfcWdOrch<DropHandler, ForwardHandler>::serializeAction(const PfcWdAction& action)
{
    SWSS_LOG_ENTER();

    const map<PfcWdAction, string> actionMap =
    {
        { PfcWdAction::PFC_WD_ACTION_FORWARD, "forward" },
        { PfcWdAction::PFC_WD_ACTION_DROP, "drop" },
        { PfcWdAction::PFC_WD_ACTION_ALERT, "alert" },
    };

    if (actionMap.find(action) == actionMap.end())
    {
        return "unknown";
    }

    return actionMap.at(action);
}


template <typename DropHandler, typename ForwardHandler>
void PfcWdOrch<DropHandler, ForwardHandler>::createEntry(const string& key,
        const vector<FieldValueTuple>& data)
{
    SWSS_LOG_ENTER();

    uint32_t detectionTime = 0;
    uint32_t restorationTime = 0;
    // According to requirements, drop action is default
    PfcWdAction action = PfcWdAction::PFC_WD_ACTION_DROP;

    Port port;
    if (!gPortsOrch->getPort(key, port))
    {
        SWSS_LOG_ERROR("Invalid port interface %s", key.c_str());
        return;
    }

    if (port.m_type != Port::PHY)
    {
        SWSS_LOG_ERROR("Interface %s is not physical port", key.c_str());
        return;
    }

    for (auto i : data)
    {
        const auto &field = fvField(i);
        const auto &value = fvValue(i);

        try
        {
            if (field == PFC_WD_DETECTION_TIME)
            {
                detectionTime = to_uint<uint32_t>(
                        value,
                        PFC_WD_DETECTION_TIME_MIN,
                        PFC_WD_DETECTION_TIME_MAX);
            }
            else if (field == PFC_WD_RESTORATION_TIME)
            {
                restorationTime = to_uint<uint32_t>(value,
                        PFC_WD_RESTORATION_TIME_MIN,
                        PFC_WD_RESTORATION_TIME_MAX);
            }
            else if (field == PFC_WD_ACTION)
            {
                action = deserializeAction(value);
                if (action == PfcWdAction::PFC_WD_ACTION_UNKNOWN)
                {
                    SWSS_LOG_ERROR("Invalid PFC Watchdog action %s", value.c_str());
                    return;
                }
            }
            else
            {
                SWSS_LOG_ERROR(
                        "Failed to parse PFC Watchdog %s configuration. Unknown attribute %s.\n",
                        key.c_str(),
                        field.c_str());
                return;
            }
        }
        catch (const exception& e)
        {
            SWSS_LOG_ERROR(
                    "Failed to parse PFC Watchdog %s attribute %s error: %s.",
                    key.c_str(),
                    field.c_str(),
                    e.what());
            return;
        }
        catch (...)
        {
            SWSS_LOG_ERROR(
                    "Failed to parse PFC Watchdog %s attribute %s. Unknown error has been occurred",
                    key.c_str(),
                    field.c_str());
            return;
        }
    }

    // Validation
    if (detectionTime == 0)
    {
        SWSS_LOG_ERROR("%s missing", PFC_WD_DETECTION_TIME);
        return;
    }

    if (!startWdOnPort(port, detectionTime, restorationTime, action))
    {
        SWSS_LOG_ERROR("Failed to start PFC Watchdog on port %s", port.m_alias.c_str());
        return;
    }

    SWSS_LOG_NOTICE("Started PFC Watchdog on port %s", port.m_alias.c_str());
}

template <typename DropHandler, typename ForwardHandler>
void PfcWdOrch<DropHandler, ForwardHandler>::deleteEntry(const string& name)
{
    SWSS_LOG_ENTER();

    Port port;
    gPortsOrch->getPort(name, port);

    if (!stopWdOnPort(port))
    {
        SWSS_LOG_ERROR("Failed to stop PFC Watchdog on port %s", name.c_str());
        return;
    }

    SWSS_LOG_NOTICE("Stopped PFC Watchdog on port %s", name.c_str());
}

template <typename DropHandler, typename ForwardHandler>
void PfcWdSwOrch<DropHandler, ForwardHandler>::createEntry(const string& key,
        const vector<FieldValueTuple>& data)
{
    SWSS_LOG_ENTER();

    if (key == PFC_WD_GLOBAL)
    {
        for (auto valuePair: data)
        {
            const auto &field = fvField(valuePair);
            const auto &value = fvValue(valuePair);

            if (field == POLL_INTERVAL_FIELD)
            {
                vector<FieldValueTuple> fieldValues;
                fieldValues.emplace_back(POLL_INTERVAL_FIELD, value);
                m_flexCounterGroupTable->set(PFC_WD_FLEX_COUNTER_GROUP, fieldValues);
            }
            else if (field == BIG_RED_SWITCH_FIELD)
            {
                SWSS_LOG_NOTICE("Recieve brs mode set, %s", value.c_str());
                setBigRedSwitchMode(value);
            }
        }
    }
    else
    {
        PfcWdOrch<DropHandler, ForwardHandler>::createEntry(key, data);
    }
}

template <typename DropHandler, typename ForwardHandler>
void PfcWdSwOrch<DropHandler, ForwardHandler>::setBigRedSwitchMode(const string value)
{
    SWSS_LOG_ENTER();

    if (value == "enable")
    {
        // When BIG_RED_SWITCH mode is enabled, pfcwd is automatically disabled
        enableBigRedSwitchMode();
    }
    else if (value == "disable")
    {
        disableBigRedSwitchMode();
    }
    else
    {
        SWSS_LOG_NOTICE("Unsupported BIG_RED_SWITCH mode set input, please use enable or disable");
    }

}

template <typename DropHandler, typename ForwardHandler>
void PfcWdSwOrch<DropHandler, ForwardHandler>::disableBigRedSwitchMode()
{
    SWSS_LOG_ENTER();

    m_bigRedSwitchFlag = false;
    // Disable pfcwdaction hanlder on each queue if exists.
    for (auto &entry : m_brsEntryMap)
    {

        if (entry.second.handler != nullptr)
        {
            SWSS_LOG_NOTICE(
                    "PFC Watchdog BIG_RED_SWITCH mode disabled on port %s, queue index %d, queue id 0x%lx and port id 0x%lx.",
                    entry.second.portAlias.c_str(),
                    entry.second.index,
                    entry.first,
                    entry.second.portId);

            entry.second.handler->commitCounters();
            entry.second.handler = nullptr;
        }

        auto queueId = entry.first;
        RedisClient redisClient(PfcWdOrch<DropHandler, ForwardHandler>::getCountersDb().get());
        string countersKey = PfcWdSwOrch<DropHandler, ForwardHandler>::getCountersTable()->getTableName() + PfcWdSwOrch<DropHandler, ForwardHandler>::getCountersTable()->getTableNameSeparator() + sai_serialize_object_id(queueId);
        redisClient.hdel(countersKey, "BIG_RED_SWITCH_MODE");
    }

    m_brsEntryMap.clear();
}

template <typename DropHandler, typename ForwardHandler>
void PfcWdSwOrch<DropHandler, ForwardHandler>::enableBigRedSwitchMode()
{
    SWSS_LOG_ENTER();

    m_bigRedSwitchFlag =  true;
    // Write to database that each queue enables BIG_RED_SWITCH
    auto allPorts = gPortsOrch->getAllPorts();

    for (auto &it: allPorts)
    {
        Port port = it.second;
        uint8_t pfcMask = 0;

        if (port.m_type != Port::PHY)
        {
            SWSS_LOG_INFO("Skip non-phy port %s", port.m_alias.c_str());
            continue;
        }

        if (!gPortsOrch->getPortPfc(port.m_port_id, &pfcMask))
        {
            SWSS_LOG_ERROR("Failed to get PFC mask on port %s", port.m_alias.c_str());
            return;
        }

        for (uint8_t i = 0; i < PFC_WD_TC_MAX; i++)
        {
            sai_object_id_t queueId = port.m_queue_ids[i];
            if ((pfcMask & (1 << i)) == 0 && m_entryMap.find(queueId) == m_entryMap.end())
            {
                continue;
            }

            string queueIdStr = sai_serialize_object_id(queueId);

            vector<FieldValueTuple> countersFieldValues;
            countersFieldValues.emplace_back("BIG_RED_SWITCH_MODE", "enable");
            PfcWdOrch<DropHandler, ForwardHandler>::getCountersTable()->set(queueIdStr, countersFieldValues);
        }
    }

    // Disable pfcwdaction handler on each queue if exists.
    for (auto & entry: m_entryMap)
    {
        if (entry.second.handler != nullptr)
        {
            entry.second.handler->commitCounters();
            entry.second.handler = nullptr;
        }
    }

    // Create pfcwdaction hanlder on all the ports.
    for (auto & it: allPorts)
    {
        Port port = it.second;
        uint8_t pfcMask = 0;

        if (port.m_type != Port::PHY)
        {
            SWSS_LOG_INFO("Skip non-phy port %s", port.m_alias.c_str());
            continue;
        }

        if (!gPortsOrch->getPortPfc(port.m_port_id, &pfcMask))
        {
            SWSS_LOG_ERROR("Failed to get PFC mask on port %s", port.m_alias.c_str());
            return;
        }

        for (uint8_t i = 0; i < PFC_WD_TC_MAX; i++)
        {
            if ((pfcMask & (1 << i)) == 0)
            {
                continue;
            }

            sai_object_id_t queueId = port.m_queue_ids[i];
            string queueIdStr = sai_serialize_object_id(queueId);

            auto entry = m_brsEntryMap.emplace(queueId, PfcWdQueueEntry(PfcWdAction::PFC_WD_ACTION_DROP, port.m_port_id, i, port.m_alias)).first;

            if (entry->second.handler== nullptr)
            {
                SWSS_LOG_NOTICE(
                        "PFC Watchdog BIG_RED_SWITCH mode enabled on port %s, queue index %d, queue id 0x%lx and port id 0x%lx.",
                        entry->second.portAlias.c_str(),
                        entry->second.index,
                        entry->first,
                        entry->second.portId);

                entry->second.handler = make_shared<DropHandler>(
                        entry->second.portId,
                        entry->first,
                        entry->second.index,
                        PfcWdOrch<DropHandler, ForwardHandler>::getCountersTable());
                entry->second.handler->initCounters();
            }
        }
    }
}

template <typename DropHandler, typename ForwardHandler>
void PfcWdSwOrch<DropHandler, ForwardHandler>::registerInWdDb(const Port& port,
        uint32_t detectionTime, uint32_t restorationTime, PfcWdAction action)
{
    SWSS_LOG_ENTER();

    uint8_t pfcMask = 0;

    if (!gPortsOrch->getPortPfc(port.m_port_id, &pfcMask))
    {
        SWSS_LOG_ERROR("Failed to get PFC mask on port %s", port.m_alias.c_str());
        return;
    }

    set<uint8_t> losslessTc;
    for (uint8_t i = 0; i < PFC_WD_TC_MAX; i++)
    {
        if ((pfcMask & (1 << i)) == 0)
        {
            continue;
        }

        losslessTc.insert(i);
    }

    if (!c_portStatIds.empty())
    {
        string key = getFlexCounterTableKey(sai_serialize_object_id(port.m_port_id));
        vector<FieldValueTuple> fieldValues;
        // Only register lossless tc counters in database.
        string str = counterIdsToStr(c_portStatIds, &sai_serialize_port_stat);
        string filteredStr = filterPfcCounters(str, losslessTc);
        fieldValues.emplace_back(PORT_COUNTER_ID_LIST, filteredStr);

        m_flexCounterTable->set(key, fieldValues);
    }

    for (auto i : losslessTc)
    {
        sai_object_id_t queueId = port.m_queue_ids[i];
        string queueIdStr = sai_serialize_object_id(queueId);

        // Store detection and restoration time for plugins
        vector<FieldValueTuple> countersFieldValues;
        countersFieldValues.emplace_back("PFC_WD_DETECTION_TIME", to_string(detectionTime * 1000));
        // Restoration time is optional
        countersFieldValues.emplace_back("PFC_WD_RESTORATION_TIME",
                restorationTime == 0 ?
                "" :
                to_string(restorationTime * 1000));
        countersFieldValues.emplace_back("PFC_WD_ACTION", this->serializeAction(action));

        PfcWdOrch<DropHandler, ForwardHandler>::getCountersTable()->set(queueIdStr, countersFieldValues);

        // We register our queues in PFC_WD table so that syncd will know that it must poll them
        vector<FieldValueTuple> queueFieldValues;

        if (!c_queueStatIds.empty())
        {
            string str = counterIdsToStr(c_queueStatIds, sai_serialize_queue_stat);
            queueFieldValues.emplace_back(QUEUE_COUNTER_ID_LIST, str);
        }

        if (!c_queueAttrIds.empty())
        {
            string str = counterIdsToStr(c_queueAttrIds, sai_serialize_queue_attr);
            queueFieldValues.emplace_back(QUEUE_ATTR_ID_LIST, str);
        }

        // Create internal entry
        m_entryMap.emplace(queueId, PfcWdQueueEntry(action, port.m_port_id, i, port.m_alias));

        string key = getFlexCounterTableKey(queueIdStr);
        m_flexCounterTable->set(key, queueFieldValues);

        // Initialize PFC WD related counters
        PfcWdActionHandler::initWdCounters(
                PfcWdOrch<DropHandler, ForwardHandler>::getCountersTable(),
                sai_serialize_object_id(queueId));
    }

    // Create egress ACL table group for each port of pfcwd's interest
    sai_object_id_t groupId;
    gPortsOrch->createBindAclTableGroup(port.m_port_id, groupId, ACL_STAGE_INGRESS);
    gPortsOrch->createBindAclTableGroup(port.m_port_id, groupId, ACL_STAGE_EGRESS);
}

template <typename DropHandler, typename ForwardHandler>
string PfcWdSwOrch<DropHandler, ForwardHandler>::filterPfcCounters(string counters, set<uint8_t>& losslessTc)
{
    SWSS_LOG_ENTER();

    istringstream is(counters);
    string counter;
    string filterCounters;

    while (getline(is, counter, ','))
    {
        size_t index = 0;
        index = counter.find(SAI_PORT_STAT_PFC_PREFIX);
        if (index != 0)
        {
            filterCounters = filterCounters + counter + ",";
        }
        else
        {
            uint8_t tc = (uint8_t)atoi(counter.substr(index + sizeof(SAI_PORT_STAT_PFC_PREFIX) - 1, 1).c_str());
            if (losslessTc.count(tc))
            {
                filterCounters = filterCounters + counter + ",";
            }
        }
    }

    if (!filterCounters.empty())
    {
        filterCounters.pop_back();
    }

    return filterCounters;
}

template <typename DropHandler, typename ForwardHandler>
string PfcWdSwOrch<DropHandler, ForwardHandler>::getFlexCounterTableKey(string key)
{
    SWSS_LOG_ENTER();

    return string(PFC_WD_FLEX_COUNTER_GROUP) + ":" + key;
}

template <typename DropHandler, typename ForwardHandler>
void PfcWdSwOrch<DropHandler, ForwardHandler>::unregisterFromWdDb(const Port& port)
{
    SWSS_LOG_ENTER();

    string key = getFlexCounterTableKey(sai_serialize_object_id(port.m_port_id));
    m_flexCounterTable->del(key);

    for (uint8_t i = 0; i < PFC_WD_TC_MAX; i++)
    {
        sai_object_id_t queueId = port.m_queue_ids[i];
        string key = getFlexCounterTableKey(sai_serialize_object_id(queueId));

        // Unregister in syncd
        m_flexCounterTable->del(key);

        auto entry = m_entryMap.find(queueId);
        if (entry != m_entryMap.end() && entry->second.handler != nullptr)
        {
            entry->second.handler->commitCounters();
        }

        m_entryMap.erase(queueId);

        // Clean up
        RedisClient redisClient(PfcWdOrch<DropHandler, ForwardHandler>::getCountersDb().get());
        string countersKey = PfcWdSwOrch<DropHandler, ForwardHandler>::getCountersTable()->getTableName() + PfcWdSwOrch<DropHandler, ForwardHandler>::getCountersTable()->getTableNameSeparator() + sai_serialize_object_id(queueId);
        redisClient.hdel(countersKey, {"PFC_WD_DETECTION_TIME", "PFC_WD_RESTORATION_TIME", "PFC_WD_ACTION", "PFC_WD_STATUS"});
    }

}

template <typename DropHandler, typename ForwardHandler>
PfcWdSwOrch<DropHandler, ForwardHandler>::PfcWdSwOrch(
        DBConnector *db,
        vector<string> &tableNames,
        const vector<sai_port_stat_t> &portStatIds,
        const vector<sai_queue_stat_t> &queueStatIds,
        const vector<sai_queue_attr_t> &queueAttrIds,
        int pollInterval):
    PfcWdOrch<DropHandler, ForwardHandler>(db, tableNames),
    m_flexCounterDb(new DBConnector(FLEX_COUNTER_DB, DBConnector::DEFAULT_UNIXSOCKET, 0)),
    m_flexCounterTable(new ProducerTable(m_flexCounterDb.get(), FLEX_COUNTER_TABLE)),
    m_flexCounterGroupTable(new ProducerTable(m_flexCounterDb.get(), FLEX_COUNTER_GROUP_TABLE)),
    c_portStatIds(portStatIds),
    c_queueStatIds(queueStatIds),
    c_queueAttrIds(queueAttrIds),
    m_pollInterval(pollInterval),
    m_applDb(make_shared<DBConnector>(APPL_DB, DBConnector::DEFAULT_UNIXSOCKET, 0)),
    m_applTable(make_shared<Table>(m_applDb.get(), APP_PFC_WD_TABLE_NAME "_INSTORM")),
    m_applDbRedisClient(m_applDb.get())
{
    SWSS_LOG_ENTER();

    string platform = getenv("platform") ? getenv("platform") : "";
    if (platform == "")
    {
        SWSS_LOG_ERROR("Platform environment variable is not defined");
        return;
    }

    string detectSha, restoreSha;
    string detectPluginName = "pfc_detect_" + platform + ".lua";
    string restorePluginName = "pfc_restore.lua";

    try
    {
        string detectLuaScript = swss::loadLuaScript(detectPluginName);
        detectSha = swss::loadRedisScript(
                PfcWdOrch<DropHandler, ForwardHandler>::getCountersDb().get(),
                detectLuaScript);

        string restoreLuaScript = swss::loadLuaScript(restorePluginName);
        restoreSha = swss::loadRedisScript(
                PfcWdOrch<DropHandler, ForwardHandler>::getCountersDb().get(),
                restoreLuaScript);

        vector<FieldValueTuple> fieldValues;
        fieldValues.emplace_back(QUEUE_PLUGIN_FIELD, detectSha + "," + restoreSha);
        fieldValues.emplace_back(POLL_INTERVAL_FIELD, to_string(m_pollInterval));
        fieldValues.emplace_back(STATS_MODE_FIELD, STATS_MODE_READ);
        m_flexCounterGroupTable->set(PFC_WD_FLEX_COUNTER_GROUP, fieldValues);
    }
    catch (...)
    {
        SWSS_LOG_WARN("Lua scripts and polling interval for PFC watchdog were not set successfully");
    }

    auto consumer = new swss::NotificationConsumer(
            PfcWdSwOrch<DropHandler, ForwardHandler>::getCountersDb().get(),
            "PFC_WD_ACTION");
    auto wdNotification = new Notifier(consumer, this, "PFC_WD_ACTION");
    Orch::addExecutor(wdNotification);
    SWSS_LOG_ERROR("Subscribe to COUNTER_DB channel \"PFC_WD_ACTION\"");

    auto interv = timespec { .tv_sec = COUNTER_CHECK_POLL_TIMEOUT_SEC, .tv_nsec = 0 };
    auto timer = new SelectableTimer(interv);
    auto executor = new ExecutableTimer(timer, this, "PFC_WD_COUNTERS_POLL");
    Orch::addExecutor(executor);
    timer->start();

    auto ssTable = new swss::SubscriberStateTable(
            m_applDb.get(), APP_PFC_WD_TABLE_NAME, TableConsumable::DEFAULT_POP_BATCH_SIZE, default_orch_pri);
    auto ssConsumer = new Consumer(ssTable, this, APP_PFC_WD_TABLE_NAME);
    Orch::addExecutor(ssConsumer);
}

template <typename DropHandler, typename ForwardHandler>
PfcWdSwOrch<DropHandler, ForwardHandler>::~PfcWdSwOrch(void)
{
    SWSS_LOG_ENTER();
    m_flexCounterGroupTable->del(PFC_WD_FLEX_COUNTER_GROUP);
}

template <typename DropHandler, typename ForwardHandler>
PfcWdSwOrch<DropHandler, ForwardHandler>::PfcWdQueueEntry::PfcWdQueueEntry(
        PfcWdAction action, sai_object_id_t port, uint8_t idx, string alias):
    action(action),
    portId(port),
    index(idx),
    portAlias(alias)
{
    SWSS_LOG_ENTER();
}

template <typename DropHandler, typename ForwardHandler>
bool PfcWdSwOrch<DropHandler, ForwardHandler>::startWdOnPort(const Port& port,
        uint32_t detectionTime, uint32_t restorationTime, PfcWdAction action)
{
    SWSS_LOG_ENTER();

    registerInWdDb(port, detectionTime, restorationTime, action);

    return true;
}

template <typename DropHandler, typename ForwardHandler>
bool PfcWdSwOrch<DropHandler, ForwardHandler>::stopWdOnPort(const Port& port)
{
    SWSS_LOG_ENTER();

    unregisterFromWdDb(port);

    return true;
}

template <typename DropHandler, typename ForwardHandler>
void PfcWdSwOrch<DropHandler, ForwardHandler>::doTask(Consumer& consumer)
{
    PfcWdOrch<DropHandler, ForwardHandler>::doTask(consumer);

    if (!PfcWdSwOrch<DropHandler, ForwardHandler>::m_entriesCreated)
    {
        return;
    }

    if ((consumer.getDbId() == APPL_DB) && (consumer.getTableName() == APP_PFC_WD_TABLE_NAME))
    {
        auto it = consumer.m_toSync.begin();
        while (it != consumer.m_toSync.end())
        {
            KeyOpFieldsValuesTuple &t = it->second;

            string &key = kfvKey(t);
            Port port;
            if (!gPortsOrch->getPort(key, port))
            {
                SWSS_LOG_ERROR("Invalid port interface %s", key.c_str());
                it = consumer.m_toSync.erase(it);
                continue;
            }
            if (port.m_type != Port::PHY)
            {
                SWSS_LOG_ERROR("Interface %s is not physical port", key.c_str());
                it = consumer.m_toSync.erase(it);
                continue;
            }

            vector<FieldValueTuple> &fvTuples = kfvFieldsValues(t);
            for (const auto &fv : fvTuples)
            {
                int qIdx = -1;
                string q = fvField(fv);
                try
                {
                    qIdx = stoi(q);
                }
                catch (const std::invalid_argument &e)
                {
                    SWSS_LOG_ERROR("Invalid argument %s to %s()", q.c_str(), e.what());
                    continue;
                }
                catch (const std::out_of_range &e)
                {
                    SWSS_LOG_ERROR("Out of range argument %s to %s()", q.c_str(), e.what());
                    continue;
                }

                if ((qIdx < 0) || (static_cast<unsigned int>(qIdx) >= port.m_queue_ids.size()))
                {
                    SWSS_LOG_ERROR("Invalid queue index %d on port %s", qIdx, key.c_str());
                    continue;
                }

                string status = fvValue(fv);
                if (status != PFC_WD_IN_STORM)
                {
                    SWSS_LOG_ERROR("Port %s queue %s not in %s", key.c_str(), q.c_str(), PFC_WD_IN_STORM);
                    continue;
                }

                SWSS_LOG_NOTICE("Port %s queue %s in status %s ", key.c_str(), q.c_str(), status.c_str());
                if (!startWdActionOnQueue(PFC_WD_IN_STORM, port.m_queue_ids[qIdx]))
                {
                    SWSS_LOG_ERROR("Failed to start PFC watchdog %s action on port %s queue %d", PFC_WD_IN_STORM, key.c_str(), qIdx);
                    continue;
                }
            }

            it = consumer.m_toSync.erase(it);
        }
    }
}

template <typename DropHandler, typename ForwardHandler>
void PfcWdSwOrch<DropHandler, ForwardHandler>::doTask(swss::NotificationConsumer& wdNotification)
{
    SWSS_LOG_ENTER();

    string queueIdStr;
    string event;
    vector<swss::FieldValueTuple> values;

    wdNotification.pop(queueIdStr, event, values);

    sai_object_id_t queueId = SAI_NULL_OBJECT_ID;
    sai_deserialize_object_id(queueIdStr, queueId);

    if (!startWdActionOnQueue(event, queueId))
    {
        SWSS_LOG_ERROR("Failed to start PFC watchdog %s event action on queue %s", event.c_str(), queueIdStr.c_str());
    }
}

template <typename DropHandler, typename ForwardHandler>
void PfcWdSwOrch<DropHandler, ForwardHandler>::doTask(SelectableTimer &timer)
{
    SWSS_LOG_ENTER();

    for (auto& handlerPair : m_entryMap)
    {
        if (handlerPair.second.handler != nullptr)
        {
            handlerPair.second.handler->commitCounters(true);
        }
    }

}

template <typename DropHandler, typename ForwardHandler>
bool PfcWdSwOrch<DropHandler, ForwardHandler>::startWdActionOnQueue(const string &event, sai_object_id_t queueId)
{
    auto entry = m_entryMap.find(queueId);
    if (entry == m_entryMap.end())
    {
        SWSS_LOG_ERROR("Queue 0x%lx is not registered", queueId);
        return false;
    }

    SWSS_LOG_NOTICE("Receive notification, %s", event.c_str());

    if (m_bigRedSwitchFlag)
    {
        SWSS_LOG_NOTICE("Big_RED_SWITCH mode is on, ingore syncd pfc watchdog notification");
    }
    else if (event == "storm")
    {
        if (entry->second.action == PfcWdAction::PFC_WD_ACTION_ALERT)
        {
            if (entry->second.handler == nullptr)
            {
                SWSS_LOG_NOTICE(
                        "PFC Watchdog detected PFC storm on port %s, queue index %d, queue id 0x%lx and port id 0x%lx.",
                        entry->second.portAlias.c_str(),
                        entry->second.index,
                        entry->first,
                        entry->second.portId);

                entry->second.handler = make_shared<PfcWdActionHandler>(
                        entry->second.portId,
                        entry->first,
                        entry->second.index,
                        PfcWdOrch<DropHandler, ForwardHandler>::getCountersTable());
                entry->second.handler->initCounters();
                // Log storm event to APPL_DB for warm-reboot purpose
                string key = m_applTable->getTableName() + m_applTable->getTableNameSeparator() + entry->second.portAlias;
                m_applDbRedisClient.hset(key, to_string(entry->second.index), PFC_WD_IN_STORM);
            }
        }
        else if (entry->second.action == PfcWdAction::PFC_WD_ACTION_DROP)
        {
            if (entry->second.handler == nullptr)
            {
                SWSS_LOG_NOTICE(
                        "PFC Watchdog detected PFC storm on port %s, queue index %d, queue id 0x%lx and port id 0x%lx.",
                        entry->second.portAlias.c_str(),
                        entry->second.index,
                        entry->first,
                        entry->second.portId);

                entry->second.handler = make_shared<DropHandler>(
                        entry->second.portId,
                        entry->first,
                        entry->second.index,
                        PfcWdOrch<DropHandler, ForwardHandler>::getCountersTable());
                entry->second.handler->initCounters();
                // Log storm event to APPL_DB for warm-reboot purpose
                string key = m_applTable->getTableName() + m_applTable->getTableNameSeparator() + entry->second.portAlias;
                m_applDbRedisClient.hset(key, to_string(entry->second.index), PFC_WD_IN_STORM);
            }
        }
        else if (entry->second.action == PfcWdAction::PFC_WD_ACTION_FORWARD)
        {
            if (entry->second.handler == nullptr)
            {
                SWSS_LOG_NOTICE(
                        "PFC Watchdog detected PFC storm on port %s, queue index %d, queue id 0x%lx and port id 0x%lx.",
                        entry->second.portAlias.c_str(),
                        entry->second.index,
                        entry->first,
                        entry->second.portId);

                entry->second.handler = make_shared<ForwardHandler>(
                        entry->second.portId,
                        entry->first,
                        entry->second.index,
                        PfcWdOrch<DropHandler, ForwardHandler>::getCountersTable());
                entry->second.handler->initCounters();
                // Log storm event to APPL_DB for warm-reboot purpose
                string key = m_applTable->getTableName() + m_applTable->getTableNameSeparator() + entry->second.portAlias;
                m_applDbRedisClient.hset(key, to_string(entry->second.index), PFC_WD_IN_STORM);
            }
        }
        else
        {
            SWSS_LOG_ERROR("Unknown PFC WD action");
            return false;
        }
    }
    else if (event == "restore")
    {
        if (entry->second.handler != nullptr)
        {
            SWSS_LOG_NOTICE(
                    "PFC Watchdog storm restored on port %s, queue index %d, queue id 0x%lx and port id 0x%lx.",
                        entry->second.portAlias.c_str(),
                        entry->second.index,
                        entry->first,
                        entry->second.portId);

            entry->second.handler->commitCounters();
            entry->second.handler = nullptr;
            // Remove storm status in APPL_DB for warm-reboot purpose
            string key = m_applTable->getTableName() + m_applTable->getTableNameSeparator() + entry->second.portAlias;
            m_applDbRedisClient.hdel(key, to_string(entry->second.index));
        }
    }
    else
    {
        SWSS_LOG_ERROR("Received unknown event from plugin, %s", event.c_str());
        return false;
    }

    return true;
}

template <typename DropHandler, typename ForwardHandler>
bool PfcWdSwOrch<DropHandler, ForwardHandler>::bake()
{
    // clean all *_last fields in COUNTERS_TABLE
    // to allow warm-reboot pfc detect & restore state machine to enter the same init state as cold-reboot
    RedisClient redisClient(PfcWdOrch<DropHandler, ForwardHandler>::getCountersDb().get());

    vector<string> cKeys;
    PfcWdSwOrch<DropHandler, ForwardHandler>::getCountersTable()->getKeys(cKeys);
    for (const auto &key : cKeys)
    {
        vector<FieldValueTuple> fvTuples;
        PfcWdSwOrch<DropHandler, ForwardHandler>::getCountersTable()->get(key, fvTuples);
        vector<string> wLasts;
        for (const auto &fv : fvTuples)
        {
            if (fvField(fv).find("_last") != string::npos)
            {
                wLasts.push_back(fvField(fv));
            }
        }
        if (!wLasts.empty())
        {
            int64_t hdel_num = redisClient.hdel(
                PfcWdSwOrch<DropHandler, ForwardHandler>::getCountersTable()->getTableName()
                + PfcWdSwOrch<DropHandler, ForwardHandler>::getCountersTable()->getTableNameSeparator()
                + key,
                wLasts);
            SWSS_LOG_NOTICE("# of hdels: %ld, table name: %s, separator: %s", hdel_num, PfcWdSwOrch<DropHandler, ForwardHandler>::getCountersTable()->getTableName().c_str(), PfcWdSwOrch<DropHandler, ForwardHandler>::getCountersTable()->getTableNameSeparator().c_str());
        }
    }

    Orch::bake();

    Consumer *consumer = dynamic_cast<Consumer *>(PfcWdSwOrch<DropHandler, ForwardHandler>::getExecutor(APP_PFC_WD_TABLE_NAME));
    if (consumer == NULL)
    {
        SWSS_LOG_ERROR("No consumer %s in Orch", APP_PFC_WD_TABLE_NAME);
        return false;
    }

    size_t refilled = consumer->refillToSync(m_applTable.get());
    SWSS_LOG_NOTICE("Add warm input PFC watchdog State: %s, %zd", APP_PFC_WD_TABLE_NAME, refilled);

    return true;
}

// Trick to keep member functions in a separate file
template class PfcWdSwOrch<PfcWdZeroBufferHandler, PfcWdLossyHandler>;
template class PfcWdSwOrch<PfcWdAclHandler, PfcWdLossyHandler>;
