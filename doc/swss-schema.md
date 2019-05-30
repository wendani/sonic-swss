Schema data is defined in ABNF [RFC5234](https://tools.ietf.org/html/rfc5234) syntax.

## Definitions of common tokens
    name                    = 1*DIGIT/1*ALPHA
    ref_hash_key_reference  = "[" hash_key "]" ;The token is a refernce to another valid DB key.
    hash_key                = name ; a valid key name (i.e. exists in DB)


## Application DB schema

### PORT_TABLE
Stores information for physical switch ports managed by the switch chip. Ports to the CPU (ie: management port) and logical ports (loopback) are not declared in the PORT_TABLE. See INTF_TABLE.

    ;Defines layer 2 ports
    ;In SONiC, Data is loaded from configuration file by portsyncd
    key                 = PORT_TABLE:ifname    ; ifname must be unique across PORT,INTF,VLAN,LAG TABLES
    admin_status        = "down" / "up"        ; admin status
    oper_status         = "down" / "up"        ; oper status
    lanes               = list of lanes ; (need format spec???)
    mac                 = 12HEXDIG      ;
    alias               = 1*64VCHAR     ; alias name of the port used by LLDP and SNMP, must be unique
    description         = 1*64VCHAR     ; port description
    speed               = 1*6DIGIT      ; port line speed in Mbps
    mtu                 = 1*4DIGIT      ; port MTU
    fec                 = 1*64VCHAR     ; port fec mode
    autoneg             = BIT           ; auto-negotiation mode

    ;QOS Mappings
    map_dscp_to_tc      = ref_hash_key_reference
    map_tc_to_queue     = ref_hash_key_reference

    Example:
    127.0.0.1:6379> hgetall PORT_TABLE:ETHERNET4
    1) "dscp_to_tc_map"
    2) "[DSCP_TO_TC_MAP_TABLE:AZURE]"
    3) "tc_to_queue_map"
    4) "[TC_TO_QUEUE_MAP_TABLE:AZURE]"

---------------------------------------------
### INTF_TABLE
cfgmgrd manages this table.  In SONiC, CPU (management) and logical ports (vlan, loopback, LAG) are declared in /etc/network/interface and /etc/sonic/config_db.json and loaded into the INTF_TABLE.

IP prefixes are formatted according to [RFC5954](https://tools.ietf.org/html/rfc5954) with a prefix length appended to the end

    ;defines logical network interfaces, an attachment to a PORT and list of 0 or more
    ;ip prefixes
    ;
    ;Status: stable
    key            = INTF_TABLE:ifname:IPprefix   ; an instance of this key will be repeated for each prefix
    IPprefix       = IPv4prefix / IPv6prefix   ; an instance of this key/value pair will be repeated for each prefix
    scope          = "global" / "local"        ; local is an interface visible on this localhost only
    if_mtu         = 1*4DIGIT                  ; MTU for the interface
    family         = "IPv4" / "IPv6"           ; address family

    IPv6prefix     =                             6( h16 ":" ) ls32
                    /                       "::" 5( h16 ":" ) ls32
                    / [               h16 ] "::" 4( h16 ":" ) ls32
                    / [ *1( h16 ":" ) h16 ] "::" 3( h16 ":" ) ls32
                    / [ *2( h16 ":" ) h16 ] "::" 2( h16 ":" ) ls32
                    / [ *3( h16 ":" ) h16 ] "::"    h16 ":"   ls32
                    / [ *4( h16 ":" ) h16 ] "::"              ls32
                    / [ *5( h16 ":" ) h16 ] "::"              h16
                    / [ *6( h16 ":" ) h16 ] "::"

     h16           = 1*4HEXDIG
     ls32          = ( h16 ":" h16 ) / IPv4address

     IPv4prefix    = dec-octet "." dec-octet "." dec-octet "." dec-octet “/” %d1-32

     dec-octet     = DIGIT                 ; 0-9
                    / %x31-39 DIGIT         ; 10-99
                    / "1" 2DIGIT            ; 100-199
                    / "2" %x30-34 DIGIT     ; 200-249
                    / "25" %x30-35          ; 250-255

For example (reorder output)

    127.0.0.1:6379> keys *
    1) "INTF_TABLE:lo:127.0.0.1/8"
    4) "INTF_TABLE:lo:::1"
    5) "INTF_TABLE:eth0:fe80::5054:ff:fece:6275/64"
    6) "INTF_TABLE:eth0:10.212.157.5/16"
    7) "INTF_TABLE:eth0.10:99.99.98.0/24"
    2) "INTF_TABLE:eth0.10:99.99.99.0/24"

    127.0.0.1:6379> HGETALL "INTF_TABLE:eth0.10:99.99.99.0/24"
    1) "scope"
    2) "global"
    3) "if_up"
    4) "1"
    5) "if_lower_up"
    6) "1"
    7) "if_mtu"
    8) "1500"
    127.0.0.1:6379> HGETALL "INTF_TABLE:eth0:fe80::5054:ff:fece:6275/64"
    1) "scope"
    2) "local"
    3) "if_up"
    4) "1"
    5) "if_lower_up"
    6) "1"
    7) "if_mtu"
    8) "65536"

---------------------------------------------
### VLAN_TABLE
    ;Defines VLANs and the interfaces which are members of the vlan
    ;Status: work in progress
    key                 = VLAN_TABLE:"Vlan"vlanid ; DIGIT 0-4095 with prefix "Vlan"
    admin_status        = "down" / "up"        ; admin status
    oper_status         = "down" / "up"        ; operating status
    mtu                 = 1*4DIGIT             ; MTU for the IP interface of the VLAN

---------------------------------------------
### LAG_TABLE
    ;a logical, link aggregation group interface (802.3ad) made of one or more ports
    ;In SONiC, data is loaded by teamsyncd
    ;Status: work in progress
    key                 = LAG_TABLE:lagname    ; logical 802.3ad LAG interface
    minimum_links       = 1*2DIGIT             ; to be implemented
    admin_status        = "down" / "up"        ; Admin status
    oper_status         = "down" / "up"        ; Oper status (physical + protocol state)
    mtu                 = 1*4DIGIT             ; MTU for this object
    linkup
    speed

    key                 = LAG_TABLE:lagname:ifname  ; physical port member of LAG, fk to PORT_TABLE:ifname
    status              = "enabled" / "disabled"    ; selected + distributing/collecting (802.3ad)
    speed               = ; set by LAG application, must match PORT_TABLE.duplex
    duplex              = ; set by LAG application, must match PORT_TABLE.duplex

For example, in a libteam implemenation, teamsyncd listens to Linux `RTM_NEWLINK` and `RTM_DELLINK` messages and creates or delete entries at the `LAG_TABLE:<team0>`

    127.0.0.1:6379> HGETALL "LAG_TABLE:team0"
    1) "admin_status"
    2) "down"
    3) "oper_status"
    4) "down"
    5) "mtu"
    6) "1500"

In addition for each team device, the teamsyncd listens to team events
and reflects the LAG ports into the redis under: `LAG_TABLE:<team0>:port`

    127.0.0.1:6379> HGETALL "LAG_TABLE:team0:veth0"
    1) "status"
    2) "disabled"
    3) "speed"
    4) "0Mbit"
    5) "duplex"
    6) "half"

---------------------------------------------
### ROUTE_TABLE
    ;Stores a list of routes
    ;Status: Mandatory
    key           = ROUTE_TABLE:prefix
    nexthop       = *prefix, ;IP addresses separated “,” (empty indicates no gateway)
    intf          = ifindex? PORT_TABLE.key  ; zero or more separated by “,” (zero indicates no interface)
    blackhole     = BIT ; Set to 1 if this route is a blackhole (or null0)

---------------------------------------------
### NEIGH_TABLE
    ; Stores the neighbors or next hop IP address and output port or
    ; interface for routes
    ; Note: neighbor_sync process will resolve mac addr for neighbors
    ; using libnl to get neighbor table
    ;Status: Mandatory
    key           = prefix PORT_TABLE.name / VLAN_INTF_TABLE.name / LAG_INTF_TABLE.name = macaddress ; (may be empty)
    neigh         = 12HEXDIG         ;  mac address of the neighbor
    family        = "IPv4" / "IPv6"  ; address family

---------------------------------------------
### FDB_TABLE

    ; Stores FDB entries which were inserted into SAI state manually
    ; Notes:
    ; - only unicast FDB entries supported
    ; - only Vlan interfaces are supported
    key           = FDB_TABLE:"Vlan"vlanid:mac_address ; mac address will be inserted to FDB for the vlan interface
    port          = ifName                ; interface where the entry is bound to
    type          = "static" / "dynamic"  ; type of the entry

    Example:
    127.0.0.1:6379> hgetall FDB_TABLE:Vlan2:52-54-00-25-06-E9
    1) "port"
    2) "Ethernet0"
    3) "type"
    4) "static"

---------------------------------------------
### QUEUE_TABLE

    ; QUEUE table. Defines port queue.
    ; SAI mapping - port queue.

    key             = "QUEUE_TABLE:"port_name":queue_index
    queue_index     = 1*DIGIT
    port_name       = ifName
    queue_reference = ref_hash_key_reference

    ;field            value
    scheduler    = ref_hash_key_reference; reference to scheduler key
    wred_profile = ref_hash_key_reference; reference to wred profile key

    Example:
    127.0.0.1:6379> hgetall QUEUE_TABLE:ETHERNET4:1
    1) "scheduler"
    2) "[SCHEDULER_TABLE:BEST_EFFORT]"
    3) "wred_profile"
    4) "[WRED_PROFILE_TABLE:AZURE]"

---------------------------------------------
### TC\_TO\_QUEUE\_MAP\_TABLE
    ; TC to queue map
    ;SAI mapping - qos_map with SAI_QOS_MAP_ATTR_TYPE == SAI_QOS_MAP_TC_TO_QUEUE. See saiqosmaps.h
    key                    = "TC_TO_QUEUE_MAP_TABLE:"name
    ;field
    tc_num = 1*DIGIT
    ;values
    queue  = 1*DIGIT; queue index

    Example:
    27.0.0.1:6379> hgetall TC_TO_QUEUE_MAP_TABLE:AZURE
    1) "5" ;tc
    2) "1" ;queue index
    3) "6"
    4) "1"

---------------------------------------------
### DSCP\_TO\_TC\_MAP\_TABLE
    ; dscp to TC map
    ;SAI mapping - qos_map object with SAI_QOS_MAP_ATTR_TYPE == sai_qos_map_type_t::SAI_QOS_MAP_DSCP_TO_TC
    key        = "DSCP_TO_TC_MAP_TABLE:"name
    ;field    value
    dscp_value = 1*DIGIT
    tc_value   = 1*DIGIT

    Example:
    127.0.0.1:6379> hgetall "DSCP_TO_TC_MAP_TABLE:AZURE"
     1) "3" ;dscp
     2) "3" ;tc
     3) "6"
     4) "5"
     5) "7"
     6) "5"
     7) "8"
     8) "7"
     9) "9"
    10) "8"

---------------------------------------------
### SCHEDULER_TABLE
    ; Scheduler table
    ; SAI mapping - saicheduler.h
    key      = "SCHEDULER_TABLE":name
    ; field     value
    type     = "DWRR"/"WRR"/"PRIORITY"
    weight   = 1*DIGIT
    priority = 1*DIGIT

    Example:
    127.0.0.1:6379> hgetall SCHEDULER_TABLE:BEST_EFFORT
    1) "type"
    2) "PRIORITY"
    3) "priority"
    4) "7"
    127.0.0.1:6379> hgetall SCHEDULER_TABLE:SCAVENGER
    1) "type"
    2) "DWRR"
    3) "weight"
    4) "35"

---------------------------------------------
### WRED\_PROFILE\_TABLE
    ; WRED profile
    ; SAI mapping - saiwred.h
    key                     = "WRED_PROFILE_TABLE:"name
    ;field                  = value
    yellow_max_threshold    = byte_count
    green_max_threshold     = byte_count
    red_max_threshold       = byte_count
    byte_count              = 1*DIGIT
    ecn                     = "ecn_none" / "ecn_green" / "ecn_yellow" / "ecn_red" /  "ecn_green_yellow" / "ecn_green_red" / "ecn_yellow_red" / "ecn_all"
    wred_green_enable       = "true" / "false"
    wred_yellow_enable      = "true" / "false"
    wred_red_enable         = "true" / "false"

    Example:
    127.0.0.1:6379> hgetall "WRED_PROFILE_TABLE:AZURE"
    1) "green_max_threshold"
    2) "20480"
    3) "yellow_max_threshold"
    4) "30720"
    5) "red_max_threshold"
    6) "1234"
    7) "ecn"
    8) "ecn_all"
    9) "wred_green_enable"
    10) "true"
    11) "wred_yellow_enable"
    12) "true"
    13) "wred_red_enable"
    14) "true"


----------------------------------------------
### TUNNEL_DECAP_TABLE
    ; Stores tunnel decap rules
    key                     = TUNNEL_DECAP_TABLE:name
    ;field                      value
    tunnel_type             = "IPINIP"
    src_ip                  = IP
    dst_ip                  = IP1,IP2 ;IP addresses separated by ","
    dscp_mode               = "uniform" / "pipe"
    ecn_mode                = "copy_from_outer" / "standard" ;standard: Behavior defined in RFC 6040 section 4.2
    ttl_mode                = "uniform" / "pipe"

    IP = dec-octet "." dec-octet "." dec-octet "." dec-octet

    "src_ip" field is optional

    Example:
    127.0.0.1:6379> hgetall TUNNEL_DECAP_TABLE:NETBOUNCER
    1) "dscp_mode"
    2) "uniform"
    3) "src_ip"
    4) "127.0.0.1"
    5) "dst_ip"
    6) "127.0.0.1"
    7) "ecn_mode"
    8) "copy_from_outer"
    9) "ttl_mode"
    10) "uniform"
    11) "tunnel_type"
    12) "IPINIP"

---------------------------------------------

### LLDP_ENTRY_TABLE
    ; current LLDP neighbor information.
    port_table_key           = LLDP_ENTRY_TABLE:ifname ; .1.0.8802.1.1.2.1
    ; field                    value
    lldp_rem_port_id_subtype = 1DIGIT     ; 4.1.1.6
    lldp_rem_port_id         = 1*255VCHAR ; 4.1.1.7
    lldp_rem_port_desc       = 0*255VCHAR ; 4.1.1.8
    lldp_rem_sys_name        = 0*255VCHAR ; 4.1.1.9

    Example:
    127.0.0.1:6379[1]> hgetall  "LLDP_ENTRY_TABLE:ETHERNET4"
    1) "lldp_rem_sys_name"
    2) "the-system-name"
    3) "lldp_rem_port_id_subtype"
    4) "6"
    5) "lldp_rem_port_id"
    6) "Ethernet7"
    7) "lldp_rem_sys_desc"
    8) "Debian - SONiC v2"

---------------------------------------------

### COPP_TABLE
Control plane policing configuration table.
The settings in this table configure trap group, which is assigned a list of trap IDs (protocols), priority of CPU queue priority, and a policer.
The CPU queue priority is strict priority.
The policer is created and exclusively owned by the given trap group; it will be not shared (bound to) any other object.

packet_action = "drop" | "forward" | "copy" | "copy_cancel" | "trap" | "log" | "deny" | "transit"

    key = "COPP_TABLE:name"
    name_list     = name | name,name_list
    queue         = number; strict queue priority. Higher number means higher priority.
    trap_ids      = name_list; Acceptable values: bgp, lacp, arp, lldp, snmp, ssh, ttl error, ip2me
    trap_action   = packet_action; trap action which will be applied to all trap_ids.

    ;Settings for embedded policer. NOTE - if no policer settings are specified, then no policer is created.
    meter_type  = "packets" | "bytes"
    mode        = "sr_tcm" | "tr_tcm" | "storm"
    color        = "aware" | "blind"
    cbs         = number ;packets or bytes depending on the meter_type value
    cir         = number ;packets or bytes depending on the meter_type value
    pbs         = number ;packets or bytes depending on the meter_type value
    pir         = number ;packets or bytes depending on the meter_type value

    green_action   = packet_action
    yellow_action  = packet_action
    red_action     = packet_action

    Example:
    127.0.0.1:6379> hgetall  "COPP_TABLE:Group.P7"
     1) "cbs"
     2) "1024"
     3) "cir"
     4) "6600"
     5) "color"
     6) "aware"
     7) "meter_type"
     8) "packets"
     9) "mode"
    10) "sr_tcm"
    11) "pbs"
    12) "1024"
    13) "pir"
    14) "4096"
    15) "red_action"
    16) "drop"
    17) "trap_ids"
    18) "lacp"
    19) "trap_action"
    20) "trap"
    127.0.0.1:6379>

Note: The configuration will be created as json file to be consumed by swssconfig tool, which will place the table into the redis database.
It's possible to create separate configuration files for different ASIC platforms.

----------------------------------------------

### ACL\_TABLE
Stores information about ACL tables on the switch.  Port names are defined in [port_config.ini](../portsyncd/port_config.ini).

    key           = ACL_TABLE:name          ; acl_table_name must be unique
    ;field        = value
    policy_desc   = 1*255VCHAR              ; name of the ACL policy table description
    type          = "mirror"/"l3"/"l3v6"    ; type of acl table, every type of
                                            ; table defines the match/action a
                                            ; specific set of match and actions.
    ports         = [0-max_ports]*port_name ; the ports to which this ACL
                                            ; table is applied, can be emtry
                                            ; value annotations
    port_name     = 1*64VCHAR               ; name of the port, must be unique
    max_ports     = 1*5DIGIT                ; number of ports supported on the chip



### ACL\_RULE\_TABLE
Stores rules associated with a specific ACL table on the switch.

    key: ACL_RULE_TABLE:table_name:rule_name   ; key of the rule entry in the table,
                                               ; seq is the order of the rules
                                               ; when the packet is filtered by the
                                               ; ACL "policy_name".
                                               ; A rule is always assocaited with a
                                               ; policy.

    ;field        = value
    priority      = 1*3DIGIT                   ; rule priority. Valid values range
                                               ; could be platform dependent

    packet_action = "forward"/"drop"/"redirect:"redirect_parameter
                                               ; an action when the fields are matched
                                               ; we have a parameter in case of packet_action="redirect"
                                               ; This parameter defines a destination for redirected packets
                                               ; it could be:
                                               : name of physical port.          Example: "Ethernet10"
                                               : name of LAG port                Example: "PortChannel5"
                                               : next-hop ip address             Example: "10.0.0.1"
                                               : next-hop group set of addresses Example: "10.0.0.1,10.0.0.3"

    mirror_action = 1*255VCHAR                 ; refer to the mirror session

    ether_type    = h16                        ; Ethernet type field

    ip_type       = ip_types                   ; options of the l2_protocol_type
                                               ; field.

    ip_protocol   = h8                         ; options of the l3_protocol_type field

    src_ip        = ipv4_prefix                ; options of the source ipv4
                                               ; address (and mask) field

    dst_ip        = ipv4_prefix                ; options of the destination ipv4
                                               ; address (and mask) field

    src_ipv6      = ipv6_prefix                ; options of the source ipv6
                                               ; address (and mask) field

    dst_ipv6      = ipv6_prefix                ; options of the destination ipv6
                                               ; address (and mask) field

    l4_src_port   = port_num                   ; source L4 port or the
    l4_dst_port   = port_num                   ; destination L4 port

    l4_src_port_range = port_num_L-port_num_H  ; source ports range of L4 ports field
    l4_dst_port_range = port_num_L-port_num_H  ; destination ports range of L4 ports field

    tcp_flags     = h8/h8                      ; TCP flags field and mask
    dscp          = h8                         ; DSCP field (only available for mirror
                                               ; table type)

    ;value annotations
    ip_types = any | ip | ipv4 | ipv4any | non_ipv4 | ipv6any | non_ipv6
    port_num      = 1*5DIGIT   ; a number between 0 and 65535
    port_num_L    = 1*5DIGIT   ; a number between 0 and 65535,
                               ; port_num_L < port_num_H
    port_num_H    = 1*5DIGIT   ; a number between 0 and 65535,
                               ; port_num_L < port_num_H
    ipv6_prefix   =                 6( h16 ":" ) ls32
       /                       "::" 5( h16 ":" ) ls32
       / [               h16 ] "::" 4( h16 ":" ) ls32
       / [ *1( h16 ":" ) h16 ] "::" 3( h16 ":" ) ls32
       / [ *2( h16 ":" ) h16 ] "::" 2( h16 ":" ) ls32
       / [ *3( h16 ":" ) h16 ] "::"    h16 ":"   ls32
       / [ *4( h16 ":" ) h16 ] "::"              ls32
       / [ *5( h16 ":" ) h16 ] "::"              h16
       / [ *6( h16 ":" ) h16 ] "::"
    h8          = 1*2HEXDIG
    h16         = 1*4HEXDIG
    ls32        = ( h16 ":" h16 ) / IPv4address
    ipv4_prefix = dec-octet "." dec-octet "." dec-octet "." dec-octet “/” %d1-32
    dec-octet   = DIGIT                     ; 0-9
                    / %x31-39 DIGIT         ; 10-99
                    / "1" 2DIGIT            ; 100-199
                    / "2" %x30-34 DIGIT     ; 200-249

Example:

    [
        {
            "ACL_TABLE:Drop_IP": {
                "policy_desc" : "Drop_Traffic",
                "type" : "L3",
                "ports" : "Ethernet0,Ethernet4"
            },
            "OP": "SET"
        },
        {
            "ACL_RULE_TABLE:Drop_IP:TheDrop": {
                "priority" : "55",
                "SRC_IP" : "20.0.0.0/25",
                "DST_IP" : "20.0.0.0/23",
                "L4_SRC_PORT" : "80",
                "PACKET_ACTION" : "DROP"
            },
            "OP": "SET"
        }
    ]

Equivalent RedisDB entry:

    127.0.0.1:6379> KEYS *ACL*
    1) "ACL_TABLE:Drop_IP"
    2) "ACL_RULE_TABLE:Drop_IP:TheDrop"
    127.0.0.1:6379> HGETALL ACL_TABLE:Drop_IP
    1) "policy_desc"
    2) "Drop_Traffic"
    3) "ports"
    4) "Ethernet0,Ethernet4"
    5) "type"
    6) "L3"
    127.0.0.1:6379> HGETALL ACL_RULE_TABLE:Drop_IP:TheDrop
     1) "DST_IP"
     2) "20.0.0.0/23"
     3) "L4_SRC_PORT"
     4) "80"
     5) "PACKET_ACTION"
     6) "DROP"
     7) "SRC_IP"
     8) "20.0.0.0/25"
     9) "priority"
    10) "55"
    127.0.0.1:6379>

----------------------------------------------

### MIRROR\_SESSION\_TABLE
Mirror session table
Stores information about mirror sessions and their properties.

    key       = MIRROR_SESSION_TABLE:mirror_session_name ; mirror_session_name is
                                                         ; unique session
                                                         ; identifier
    ; field   = value
    status    = "active"/"inactive"   ; Session state.
    src_ip    = ipv4_address          ; Session souce IP address
    dst_ip    = ipv4_address          ; Session destination IP address
    gre_type  = h16                   ; Session GRE protocol type
    dscp      = h8                    ; Session DSCP
    ttl       = h8                    ; Session TTL
    queue     = h8                    ; Session output queue
    policer   = policer_name          ; Session policer name

    ;value annotations
    mirror_session_name = 1*255VCHAR
    policer_name        = 1*255VCHAR
    h8                  = 1*2HEXDIG
    h16                 = 1*4HEXDIG
    ipv4_address        = dec-octet "." dec-octet "." dec-octet "." dec-octet “/” %d1-32
    dec-octet           = DIGIT                     ; 0-9
                           / %x31-39 DIGIT         ; 10-99
                           / "1" 2DIGIT            ; 100-199
                           / "2" %x30-34 DIGIT     ; 200-249

Example:

    [
        {
            "MIRROR_SESSION_TABLE:session_1": {
                "src_ip": "1.1.1.1",
                "dst_ip": "2.2.2.2",
                "gre_type": "0x6558",
                "dscp": "50",
                "ttl": "64",
                "queue": "0"
            },
            "OP": "SET"
        }
    ]

Equivalent RedisDB entry:

    127.0.0.1:6379> KEYS *MIRROR*
    1) "MIRROR_SESSION_TABLE:session_1"
    127.0.0.1:6379> HGETALL MIRROR_SESSION_TABLE:session_1
     1) "src_ip"
     2) "1.1.1.1"
     3) "dst_ip"
     4) "2.2.2.2
     5) "gre_type"
     6) "0x6558"
     7) "dscp"
     8) "50"
     9) "ttl"
    10) "64"
    11) "queue"
    12) "0"

---------------------------------------------

### POLICER_TABLE
Policer table
Stores information about policers and their properties.

packet_action = "drop" | "forward" | "copy" | "copy_cancel" | "trap" | "log" | "deny" | "transit"

    ;Key
    key = "POLICER_TABLE:name"

    ;Field-Value tuples
    meter_type  = "packets" | "bytes"
    mode        = "sr_tcm" | "tr_tcm" | "storm"
    color       = "aware" | "blind"
    cbs         = number ;packets or bytes depending on the meter_type value
    cir         = number ;packets or bytes depending on the meter_type value
    pbs         = number ;packets or bytes depending on the meter_type value
    pir         = number ;packets or bytes depending on the meter_type value

    green_action   = packet_action
    yellow_action  = packet_action
    red_action     = packet_action

    Example:
    127.0.0.1:6379> hgetall "POLICER_TABLE:POLICER_1"
     1) "cbs"
     2) "600"
     3) "cir"
     4) "600"
     5) "meter_type"
     6) "packets"
     7) "mode"
     8) "sr_tcm"
     9) "red_action"
    10) "drop"

----------------------------------------------

### VXLAN\_TUNNEL\_MAP
    ;Stores vxlan tunnel map configuration. Defines mapping between vxlan vni and vrf

    key       = VXLAN_TUNNEL_MAP:tunnel_name:tunnel_map_name
                                                ; tunnel_name is a reference to created vxlan tunnel
                                                ; tunnel_map_name is an arbitrary name of the map
    vni       = 1*8DIGIT                        ; vni id, defined for tunnel map
    vrf       = vrf_name                        ; name of the vrf

### VNET\_ROUTE\_TUNNEL_TABLE
    ;Defines schema for VNet Route tunnel table attributes

    key                        = VNET_ROUTE_TUNNEL_TABLE:vnet_name:prefix
                                                ; Vnet route tunnel table with prefix
    ; field                      value
    endpoint                   = IP             ; Host VM IP address
    mac_address                = 12HEXDIG       ; Inner dest mac in encapsulated packet (Optional)
    vxlanid                    = 1*8DIGIT       ; VNI value in encapsulated packet (Optional)

    ;value annotations
    vnet_name                  = 1*16VCHAR

### VNET\_ROUTE_TABLE
    ;Defines schema for VNet Route table attributes
    key                        = VNET_ROUTE_TABLE:vnet_name:prefix
                                                ; Vnet route table with prefix
    ;field                       value
    nexthop                    = IP             ; Nexthop IP address (Optional)
    ifname                     = ifname         ; Interface name

## Configuration DB schema

### PORT_TABLE
Stores information for physical switch ports managed by the switch chip. Ports to the CPU (ie: management port) and logical ports (loopback) are not declared in the PORT_TABLE. See MGMT_PORT.

    ;Configuration for layer 2 ports
    key                 = PORT|ifname   ; ifname must be unique across PORT,INTF,VLAN,LAG TABLES
    admin_status        = "down" / "up" ; admin status
    lanes               = list of lanes ; (need format spec???)
    mac                 = 12HEXDIG      ;
    alias               = 1*64VCHAR     ; alias name of the port used by LLDP and SNMP, must be unique
    description         = 1*64VCHAR     ; port description
    speed               = 1*6DIGIT      ; port line speed in Mbps
    mtu                 = 1*4DIGIT      ; port MTU
    fec                 = 1*64VCHAR     ; port fec mode
    autoneg             = BIT           ; auto-negotiation mode

### MGMT_PORT_TABLE
    ;Configuration for management port, including at least one key
    key                 = MGMT_PORT|ifname    ; ifname must be unique across PORT,INTF,VLAN,LAG TABLES
    admin_status        = "down" / "up" ; admin status
    mac                 = 12HEXDIG      ;
    alias               = 1*64VCHAR     ; alias name of the port used by LLDP and SNMP, must be unique
    description         = 1*64VCHAR     ; port description
    speed               = 1*6DIGIT      ; port line speed in Mbps
    mtu                 = 1*4DIGIT      ; port MTU
    fec                 = 1*64VCHAR     ; port fec mode
    autoneg             = BIT           ; auto-negotiation mode

### WARM\_RESTART
    ;Stores system warm start configuration
    ;Status: work in progress

    key                 = WARM_RESTART:name ; name is the name of SONiC docker or "system" for global configuration.

    neighsyncd_timer    = 1*4DIGIT          ; neighsyncd_timer is the timer used for neighsyncd during the warm restart.
                                            ; Timer is started after we restored the neighborTable to internal data structures.
                                            ; neighborsyncd then starts to read all linux kernel entries and mark the entries in
                                            ; the data structures accordingly. Once the timer is expired, we will do reconciliation
                                            ; and push the delta to appDB
                                            ; Valid value is 1-9999. 0 is invalid.

    bgp_timer           = 1*4DIGIT          ; bgp_timer holds the time interval utilized by fpmsyncd during warm-restart episodes.
                                            ; During this interval fpmsyncd will recover all the routing state previously pushed to
                                            ; AppDB, as well as all the new state coming from zebra/bgpd. Upon expiration of this
                                            ; timer, fpmsyncd will execute the reconciliation logic to eliminate all the staled
                                            ; state from AppDB. This timer should match the BGP-GR restart-timer configured within
                                            ; the elected routing-stack.
                                            ; Supported range: 1-3600.

    teamsyncd_timer     = 1*4DIGIT          ; teamsyncd_timer holds the time interval utilized by teamsyncd during warm-restart episodes.
                                            ; The timer is started when teamsyncd starts. During the timer interval teamsyncd
                                            ; will preserver all LAG interface changes, but it will not apply them. The changes
                                            ; will only be applied when the timer expired. During the changes application the stale
                                            ; LAG entries will be removed, the new LAG entries will be created.
                                            ; Supported range: 1-9999. 0 is invalid


### VXLAN\_TUNNEL
Stores vxlan tunnels configuration
Status: ready

    key       = VXLAN_TUNNEL:name               ; name is an arbitrary name of vxlan tunnel
    src_ip    = ipv4_address                    ; tunnel source IP address. Mandatory
    dst_ip    = ipv4_address                    ; tunnel destination IP address. Optional. When this attribute is omitted or equal to "0.0.0.0"
                                                ; the created tunnel will be P2MP. Otherwise the created tunnel will be P2P

### VXLAN\_TUNNEL\_MAP
Stores vxlan tunnel map configuration. Defines mapping between vxlan vni and vlan interface
Status: ready

    key       = VXLAN_TUNNEL_MAP:tunnel_name:tunnel_map_name
                                                ; tunnel_name is a reference to created vxlan tunnel
                                                ; tunnel_map_name is an arbitrary name of the map
    vni       = uint24                          ; vni id, defined for tunnel map
    vlan      = "Vlan"vlan_id                   ; name of the existing vlan interface

### NEIGH_TABLE
    ; Stores the neighbors. Defines static configuration of neighbor entries. If mac address is not specified, implementation shall resolve the mac-address for the neighbor IP.
    key           = NEIGH|PORT_TABLE.name / VLAN_INTF_TABLE.name / LAG_INTF_TABLE.name|prefix
    neigh         = 12HEXDIG         ; mac address of the neighbor (optional)
    family        = "IPv4" / "IPv6"  ; address family

## State DB schema

### PORT_TABLE
Stores information for physical switch ports managed by the switch chip. Ports to the CPU (ie: management port) and logical ports (loopback) are not declared in the PORT_TABLE. See MGMT_PORT.

    ;State for layer 2 ports
    key                 = PORT_TABLE|ifname    ; ifname must be unique across PORT,INTF,VLAN,LAG TABLES
    oper_status         = "down" / "up" ; oper status
    state               = "" / "ok"     ; port created successfully

### MGMT_PORT_TABLE
    ;State for management port, including at least one key
    key                 = MGMT_PORT_TABLE|ifname    ; ifname must be unique across PORT,INTF,VLAN,LAG TABLES
    oper_status         = "down" / "up" ; oper status

### WARM\_RESTART\_ENABLE\_TABLE
    ;Stores system warm start and docker warm start enable/disable configuration
    ;The configuration is persistent across warm reboot but not cold reboot.
    ;Status: work in progress

    key                 = WARM_RESTART_ENABLE_TABLE:name ; name is the name of SONiC docker or "system" for global configuration.

    enable              = "true" / "false"  ; Default value as false.
                                            ; If "system" warm start knob is true, docker level knob will be ignored.
                                            ; If "system" warm start knob is false, docker level knob takes effect.

### WARM\_RESTART\_TABLE
    ;Stores application and orchdameon warm start status
    ;Status: work in progress

    key             = WARM_RESTART_TABLE:process_name         ; process_name is a unique process identifier.
                                                              ; with exception of 'warm-shutdown' operation.
                                                              ; 'warm-shutdown' operation key is used to
                                                              ; track warm shutdown stages and results.
                                                              ; Added to this table to leverage the existing
                                                              ; "show warm-restart state" command.

    restore_count   = 1*10DIGIT                               ; a value between 0 and 2147483647 to keep track
                                                              ; of the number of times that an application has
                                                              ; 'restored' its state from its associated redis
                                                              ; data-store; which is equivalent to the number
                                                              ; of times an application has iterated through
                                                              ; a warm-restart cycle.

    state           = "initialized" / "restored" / "reconciled"  ; initialized: initial FSM state for processes
                                                                 ; with warm-restart capabilities turned on.
                                                                 ;
                                                                 ; restored: process restored the state previously
                                                                 ; uploaded to redis data-stores.
                                                                 ;
                                                                 ; reconciled: process reconciled 'old' and 'new'
                                                                 ; state collected in 'restored' phase. Examples:
                                                                 ; dynanic data like port state, neighbor, routes
                                                                 ; and so on.

### NEIGH_RESTORE_TABLE
    ;State for neighbor table restoring process during warm reboot
    key                 = NEIGH_RESTORE_TABLE|Flags
    restored            = "true" / "false" ; restored state

## Configuration files
What configuration files should we have?  Do apps, orch agent each need separate files?

[port_config.ini](https://github.com/stcheng/swss/blob/mock/portsyncd/port_config.ini) - defines physical port information

portsyncd reads from port_config.ini and updates PORT_TABLE in APP_DB
