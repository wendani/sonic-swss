#ifndef SWSS_BUFFORCH_H
#define SWSS_BUFFORCH_H

#include <string>
#include <map>
#include <unordered_map>
#include "orch.h"
#include "portsorch.h"
#include "redisapi.h"
#include "redisclient.h"

#define BUFFER_POOL_WATERMARK_STAT_COUNTER_FLEX_COUNTER_GROUP "BUFFER_POOL_WATERMARK_STAT_COUNTER"

const string buffer_size_field_name         = "size";
const string buffer_pool_type_field_name    = "type";
const string buffer_pool_mode_field_name    = "mode";
const string buffer_pool_field_name         = "pool";
const string buffer_pool_mode_dynamic_value = "dynamic";
const string buffer_pool_mode_static_value  = "static";
const string buffer_pool_xoff_field_name    = "xoff";
const string buffer_xon_field_name          = "xon";
const string buffer_xon_offset_field_name   = "xon_offset";
const string buffer_xoff_field_name         = "xoff";
const string buffer_dynamic_th_field_name   = "dynamic_th";
const string buffer_static_th_field_name    = "static_th";
const string buffer_profile_field_name      = "profile";
const string buffer_value_ingress           = "ingress";
const string buffer_value_egress            = "egress";
const string buffer_profile_list_field_name = "profile_list";

class BufferOrch : public Orch
{
public:
    BufferOrch(DBConnector *db, vector<string> &tableNames);
    bool isPortReady(const std::string& port_name) const;
    static type_map m_buffer_type_maps;
    void generateBufferPoolWatermarkCounterIdList(void);
    const object_map &getBufferPoolNameOidMap(void);

private:
    typedef task_process_status (BufferOrch::*buffer_table_handler)(Consumer& consumer);
    typedef map<string, buffer_table_handler> buffer_table_handler_map;
    typedef pair<string, buffer_table_handler> buffer_handler_pair;

    void doTask() override;
    virtual void doTask(Consumer& consumer);
    void initTableHandlers();
    void initBufferReadyLists(DBConnector *db);
    void initBufferReadyList(Table& table);
    void initFlexCounterGroupTable(void);
    task_process_status processBufferPool(Consumer &consumer);
    task_process_status processBufferProfile(Consumer &consumer);
    task_process_status processQueue(Consumer &consumer);
    task_process_status processPriorityGroup(Consumer &consumer);
    task_process_status processIngressBufferProfileList(Consumer &consumer);
    task_process_status processEgressBufferProfileList(Consumer &consumer);

    buffer_table_handler_map m_bufferHandlerMap;
    std::unordered_map<std::string, bool> m_ready_list;
    std::unordered_map<std::string, std::vector<std::string>> m_port_ready_list_ref;

    unique_ptr<DBConnector> m_flexCounterDb;
    unique_ptr<ProducerTable> m_flexCounterGroupTable;
    unique_ptr<ProducerTable> m_flexCounterTable;

    unique_ptr<DBConnector> m_countersDb;
    RedisClient m_countersDbRedisClient;

    bool m_isBufferPoolWatermarkCounterIdListGenerated = false;
};
#endif /* SWSS_BUFFORCH_H */

