import json
import time

from dvslib.dvs_common import wait_for_result
from swsscommon import swsscommon

DEFAULT_MTU = "9100"

CFG_VLAN_SUB_INTF_TABLE_NAME = "VLAN_SUB_INTERFACE"
CFG_PORT_TABLE_NAME = "PORT"
CFG_LAG_TABLE_NAME = "PORTCHANNEL"
CFG_LAG_MEMBER_TABLE_NAME = "PORTCHANNEL_MEMBER"
CFG_VRF_TABLE_NAME = "VRF"
CFG_VXLAN_TUNNEL_TABLE_NAME = "VXLAN_TUNNEL"
CFG_VNET_TABLE_NAME = "VNET"

STATE_PORT_TABLE_NAME = "PORT_TABLE"
STATE_LAG_TABLE_NAME = "LAG_TABLE"
STATE_INTERFACE_TABLE_NAME = "INTERFACE_TABLE"

APP_INTF_TABLE_NAME = "INTF_TABLE"
APP_ROUTE_TABLE_NAME = "ROUTE_TABLE"
APP_PORT_TABLE_NAME = "PORT_TABLE"
APP_LAG_TABLE_NAME = "LAG_TABLE"
APP_VNET_TABLE_NAME = "VNET_TABLE"

ASIC_RIF_TABLE = "ASIC_STATE:SAI_OBJECT_TYPE_ROUTER_INTERFACE"
ASIC_ROUTE_ENTRY_TABLE = "ASIC_STATE:SAI_OBJECT_TYPE_ROUTE_ENTRY"
ASIC_NEXT_HOP_TABLE = "ASIC_STATE:SAI_OBJECT_TYPE_NEXT_HOP"
ASIC_NEXT_HOP_GROUP_TABLE = "ASIC_STATE:SAI_OBJECT_TYPE_NEXT_HOP_GROUP"
ASIC_NEXT_HOP_GROUP_MEMBER_TABLE = "ASIC_STATE:SAI_OBJECT_TYPE_NEXT_HOP_GROUP_MEMBER"
ASIC_LAG_MEMBER_TABLE = "ASIC_STATE:SAI_OBJECT_TYPE_LAG_MEMBER"
ASIC_HOSTIF_TABLE = "ASIC_STATE:SAI_OBJECT_TYPE_HOSTIF"
ASIC_VIRTUAL_ROUTER_TABLE = "ASIC_STATE:SAI_OBJECT_TYPE_VIRTUAL_ROUTER"
ASIC_TUNNEL_TABLE = "ASIC_STATE:SAI_OBJECT_TYPE_TUNNEL"

ADMIN_STATUS = "admin_status"
VRF_NAME = "vrf_name"
VNET_NAME = "vnet_name"
SRC_IP = "src_ip"
VXLAN_TUNNEL = "vxlan_tunnel"
VNI = "vni"
PEER_LIST = "peer_list"

ETHERNET_PREFIX = "Ethernet"
LAG_PREFIX = "PortChannel"
VRF_PREFIX = "Vrf"
VNET_PREFIX = "Vnet"

VLAN_SUB_INTERFACE_SEPARATOR = "."
APPL_DB_SEPARATOR = ":"


class TestSubPortIntf(object):
    SUB_PORT_INTERFACE_UNDER_TEST = "Ethernet64.10"
    LAG_SUB_PORT_INTERFACE_UNDER_TEST = "PortChannel1.20"
    LAG_MEMBERS_UNDER_TEST = ["Ethernet68", "Ethernet72"]

    IPV4_ADDR_UNDER_TEST = "10.0.0.33/31"
    IPV4_TOME_UNDER_TEST = "10.0.0.33/32"
    IPV4_SUBNET_UNDER_TEST = "10.0.0.32/31"

    IPV6_ADDR_UNDER_TEST = "fc00::41/126"
    IPV6_TOME_UNDER_TEST = "fc00::41/128"
    IPV6_SUBNET_UNDER_TEST = "fc00::40/126"

    VRF_UNDER_TEST = "Vrf0"

    TUNNEL_UNDER_TEST = "Tunnel1"
    VTEP_IP_UNDER_TEST = "1.1.1.1"
    VNET_UNDER_TEST = "Vnet1000"
    VNI_UNDER_TEST = "1000"

    def connect_dbs(self, dvs):
        self.app_db = dvs.get_app_db()
        self.asic_db = dvs.get_asic_db()
        self.config_db = dvs.get_config_db()
        self.state_db = dvs.get_state_db()
        dvs.setup_db()

        self.default_vrf_oid = self.get_default_vrf_oid()

    def get_parent_port_index(self, port_name):
        if port_name.startswith(ETHERNET_PREFIX):
            idx = int(port_name[len(ETHERNET_PREFIX):])
        else:
            assert port_name.startswith(LAG_PREFIX)
            idx = int(port_name[len(LAG_PREFIX):])
        return idx

    def set_parent_port_oper_status(self, dvs, port_name, status):
        if port_name.startswith(ETHERNET_PREFIX):
            srv_idx = self.get_parent_port_index(port_name) // 4
            dvs.servers[srv_idx].runcmd("ip link set dev eth0 " + status)
        else:
            assert port_name.startswith(LAG_PREFIX)
            dvs.runcmd("bash -c 'echo " + ("1" if status == "up" else "0") +
                       " > /sys/class/net/" + port_name + "/carrier'")
        time.sleep(1)

    def set_parent_port_admin_status(self, dvs, port_name, status):
        fvs = {ADMIN_STATUS: status}

        if port_name.startswith(ETHERNET_PREFIX):
            tbl_name = CFG_PORT_TABLE_NAME
        else:
            assert port_name.startswith(LAG_PREFIX)
            tbl_name = CFG_LAG_TABLE_NAME
        self.config_db.create_entry(tbl_name, port_name, fvs)

        if port_name.startswith(ETHERNET_PREFIX):
            self.set_parent_port_oper_status(dvs, port_name, "down")
            self.set_parent_port_oper_status(dvs, port_name, "up")
        else:
            self.set_parent_port_oper_status(dvs, port_name, "up")

    def create_vxlan_tunnel(self, tunnel_name, vtep_ip):
        fvs = {
            SRC_IP: vtep_ip,
        }
        self.config_db.create_entry(CFG_VXLAN_TUNNEL_TABLE_NAME, tunnel_name, fvs)

    def create_vnet(self, vnet_name, tunnel_name, vni, peer_list=""):
        fvs = {
            VXLAN_TUNNEL: tunnel_name,
            VNI: vni,
            PEER_LIST: peer_list,
        }
        self.config_db.create_entry(CFG_VNET_TABLE_NAME, vnet_name, fvs)

    def create_vrf(self, vrf_name):
        if vrf_name.startswith(VRF_PREFIX):
            self.config_db.create_entry(CFG_VRF_TABLE_NAME, vrf_name, {"NULL": "NULL"})
        else:
            assert vrf_name.startswith(VNET_PREFIX)
            self.create_vxlan_tunnel(self.TUNNEL_UNDER_TEST, self.VTEP_IP_UNDER_TEST)
            self.create_vnet(vrf_name, self.TUNNEL_UNDER_TEST, self.VNI_UNDER_TEST)

    def create_sub_port_intf_profile(self, sub_port_intf_name, vrf_name=None):
        fvs = {ADMIN_STATUS: "up"}
        if vrf_name:
            fvs[VRF_NAME if vrf_name.startswith(VRF_PREFIX) else VNET_NAME] = vrf_name

        self.config_db.create_entry(CFG_VLAN_SUB_INTF_TABLE_NAME, sub_port_intf_name, fvs)

    def add_lag_members(self, lag, members):
        fvs = {"NULL": "NULL"}

        for member in members:
            key = "{}|{}".format(lag, member)
            self.config_db.create_entry(CFG_LAG_MEMBER_TABLE_NAME, key, fvs)

    def create_sub_port_intf_profile_appl_db(self, sub_port_intf_name, admin_status, vrf_name=None):
        pairs = [
            (ADMIN_STATUS, admin_status),
            ("mtu", "0"),
        ]
        if vrf_name:
            pairs.append((VRF_NAME if vrf_name.startswith(VRF_PREFIX) else VNET_NAME, vrf_name))
        fvs = swsscommon.FieldValuePairs(pairs)

        tbl = swsscommon.ProducerStateTable(self.app_db.db_connection, APP_INTF_TABLE_NAME)
        tbl.set(sub_port_intf_name, fvs)

    def add_sub_port_intf_ip_addr(self, sub_port_intf_name, ip_addr):
        fvs = {"NULL": "NULL"}

        key = "{}|{}".format(sub_port_intf_name, ip_addr)
        self.config_db.create_entry(CFG_VLAN_SUB_INTF_TABLE_NAME, key, fvs)

    def add_sub_port_intf_ip_addr_appl_db(self, sub_port_intf_name, ip_addr):
        pairs = [
            ("scope", "global"),
            ("family", "IPv4" if "." in ip_addr else "IPv6"),
        ]
        fvs = swsscommon.FieldValuePairs(pairs)

        tbl = swsscommon.ProducerStateTable(self.app_db.db_connection, APP_INTF_TABLE_NAME)
        tbl.set(sub_port_intf_name + APPL_DB_SEPARATOR + ip_addr, fvs)

    def set_sub_port_intf_admin_status(self, sub_port_intf_name, status):
        fvs = {ADMIN_STATUS: status}

        self.config_db.create_entry(CFG_VLAN_SUB_INTF_TABLE_NAME, sub_port_intf_name, fvs)

    def remove_vxlan_tunnel(self, tunnel_name):
        self.config_db.delete_entry(CFG_VXLAN_TUNNEL_TABLE_NAME, tunnel_name)

    def remove_vnet(self, vnet_name):
        self.config_db.delete_entry(CFG_VNET_TABLE_NAME, vnet_name)

    def remove_vrf(self, vrf_name):
        if vrf_name.startswith(VRF_PREFIX):
            self.config_db.delete_entry(CFG_VRF_TABLE_NAME, vrf_name)
        else:
            assert vrf_name.startswith(VNET_PREFIX)
            self.remove_vnet(vrf_name)

    def check_vrf_removal(self, vrf_oid):
        self.asic_db.wait_for_deleted_keys(ASIC_VIRTUAL_ROUTER_TABLE, [vrf_oid])

    def remove_lag_members(self, lag, members):
        for member in members:
            key = "{}|{}".format(lag, member)
            self.config_db.delete_entry(CFG_LAG_MEMBER_TABLE_NAME, key)

    def remove_sub_port_intf_profile(self, sub_port_intf_name):
        self.config_db.delete_entry(CFG_VLAN_SUB_INTF_TABLE_NAME, sub_port_intf_name)

    def check_sub_port_intf_profile_removal(self, rif_oid):
        self.asic_db.wait_for_deleted_keys(ASIC_RIF_TABLE, [rif_oid])

    def remove_sub_port_intf_profile_appl_db(self, sub_port_intf_name):
        tbl = swsscommon.ProducerStateTable(self.app_db.db_connection, APP_INTF_TABLE_NAME)
        tbl._del(sub_port_intf_name)

    def remove_sub_port_intf_ip_addr(self, sub_port_intf_name, ip_addr):
        key = "{}|{}".format(sub_port_intf_name, ip_addr)
        self.config_db.delete_entry(CFG_VLAN_SUB_INTF_TABLE_NAME, key)

    def check_sub_port_intf_ip_addr_removal(self, sub_port_intf_name, ip_addrs):
        interfaces = ["{}:{}".format(sub_port_intf_name, addr) for addr in ip_addrs]
        self.app_db.wait_for_deleted_keys(APP_INTF_TABLE_NAME, interfaces)

    def remove_sub_port_intf_ip_addr_appl_db(self, sub_port_intf_name, ip_addr):
        tbl = swsscommon.ProducerStateTable(self.app_db.db_connection, APP_INTF_TABLE_NAME)
        tbl._del(sub_port_intf_name + APPL_DB_SEPARATOR + ip_addr)

    def get_oids(self, table):
        return self.asic_db.get_keys(table)

    def get_newly_created_oid(self, table, old_oids):
        new_oids = self.asic_db.wait_for_n_keys(table, len(old_oids) + 1)
        oid = [ids for ids in new_oids if ids not in old_oids]
        return oid[0]

    def get_default_vrf_oid(self):
        oids = self.get_oids(ASIC_VIRTUAL_ROUTER_TABLE)
        assert len(oids) == 1, "Wrong # of default vrfs: %d, expected #: 1." % (len(oids))
        return oids[0]

    def get_ip_prefix_nhg_oid(self, ip_prefix, vrf_oid=None):
        if vrf_oid is None:
            vrf_oid = self.default_vrf_oid

        def _access_function():
            route_entry_found = False

            raw_route_entry_keys = self.asic_db.get_keys(ASIC_ROUTE_ENTRY_TABLE)
            for raw_route_entry_key in raw_route_entry_keys:
                route_entry_key = json.loads(raw_route_entry_key)
                if route_entry_key["dest"] == ip_prefix:
                    route_entry_found = True
                    assert route_entry_key["vr"] == vrf_oid
                    break

            return (route_entry_found, raw_route_entry_key)

        (route_entry_found, raw_route_entry_key) = wait_for_result(_access_function)

        fvs = self.asic_db.get_entry(ASIC_ROUTE_ENTRY_TABLE, raw_route_entry_key)

        nhg_oid = fvs.get("SAI_ROUTE_ENTRY_ATTR_NEXT_HOP_ID", "")
        assert nhg_oid != ""
        assert nhg_oid != "oid:0x0"

        return nhg_oid

    def check_sub_port_intf_key_existence(self, db, table_name, key):
        db.wait_for_matching_keys(table_name, [key])

    def check_sub_port_intf_fvs(self, db, table_name, key, fv_dict):
        db.wait_for_field_match(table_name, key, fv_dict)

    def check_sub_port_intf_route_entries(self, vrf_oid=None, check_ipv6=True):
        expected_dests = [self.IPV4_TOME_UNDER_TEST,
                          self.IPV4_SUBNET_UNDER_TEST,
                          self.IPV6_TOME_UNDER_TEST,
                          self.IPV6_SUBNET_UNDER_TEST]
        if not check_ipv6:
            expected_dests.pop()
            expected_dests.pop()
        if vrf_oid is None:
            vrf_oid = self.default_vrf_oid
        expected_vrf_oids = [vrf_oid,
                             vrf_oid,
                             vrf_oid,
                             vrf_oid]
        if not check_ipv6:
            expected_vrf_oids.pop()
            expected_vrf_oids.pop()

        def _access_function():
            raw_route_entries = self.asic_db.get_keys(ASIC_ROUTE_ENTRY_TABLE)
            route_dest_vrf_oids = [(json.loads(raw_route_entry)["dest"], json.loads(raw_route_entry)["vr"])
                                        for raw_route_entry in raw_route_entries]
            return (all((dest, vrf_oid) in route_dest_vrf_oids for dest, vrf_oid in zip(expected_dests, expected_vrf_oids)), None)

        wait_for_result(_access_function)

    def check_sub_port_intf_mtu_kernel(self, dvs, port_name, mtu):
        (ec, out) = dvs.runcmd(['bash', '-c', "ip link show {} | grep 'mtu {}'".format(port_name, mtu)])
        assert ec == 0
        assert mtu in out

    def check_sub_port_intf_admin_status_kernel(self, dvs, port_name, admin_up):
        up = "UP"
        if admin_up == True:
            up = "," + up
        (ec, out) = dvs.runcmd(['bash', '-c', "ip link show {} | grep {}".format(port_name, up)])
        if admin_up == True:
            assert ec == 0
            assert up in out
        else:
            assert ec == 1
            assert up not in out

    def check_sub_port_intf_vrf_bind_kernel(self, dvs, port_name, vrf_name):
        (ec, out) = dvs.runcmd(['bash', '-c', "ip link show {} | grep {}".format(port_name, vrf_name)])
        assert ec == 0
        assert vrf_name in out

    def check_sub_port_intf_vrf_nobind_kernel(self, dvs, port_name, vrf_name=None):
        if vrf_name is not None:
            (ec, out) = dvs.runcmd(['bash', '-c', "ip link show {} | grep {}".format(port_name, vrf_name)])
            assert ec == 1
            assert vrf_name not in out

        (ec, out) = dvs.runcmd(['bash', '-c', "ip link show {} | grep master".format(port_name)])
        assert ec == 1
        assert "master" not in out

    def check_sub_port_intf_removal_kernel(self, dvs, port_name):
        (ec, out) = dvs.runcmd(['bash', '-c', "ip link show {}".format(port_name)])
        assert ec == 1
        assert port_name in out
        assert "does not exist" in out

    def check_sub_port_intf_key_removal(self, db, table_name, key):
        db.wait_for_deleted_keys(table_name, [key])

    def check_sub_port_intf_route_entries_removal(self, removed_route_entries):
        def _access_function():
            raw_route_entries = self.asic_db.get_keys(ASIC_ROUTE_ENTRY_TABLE)
            status = all(str(json.loads(raw_route_entry)["dest"])
                         not in removed_route_entries
                         for raw_route_entry in raw_route_entries)
            return (status, None)

        wait_for_result(_access_function)

    def _test_sub_port_intf_creation(self, dvs, sub_port_intf_name, vrf_name=None):
        substrs = sub_port_intf_name.split(VLAN_SUB_INTERFACE_SEPARATOR)
        parent_port = substrs[0]
        vlan_id = substrs[1]
        if parent_port.startswith(ETHERNET_PREFIX):
            state_tbl_name = STATE_PORT_TABLE_NAME
            phy_ports = [parent_port]
        else:
            assert parent_port.startswith(LAG_PREFIX)
            state_tbl_name = STATE_LAG_TABLE_NAME
            phy_ports = self.LAG_MEMBERS_UNDER_TEST

        vrf_oid = self.default_vrf_oid
        old_rif_oids = self.get_oids(ASIC_RIF_TABLE)

        self.set_parent_port_admin_status(dvs, parent_port, "up")
        # Add lag members to test physical port host interface vlan tag attribute
        if parent_port.startswith(LAG_PREFIX):
            self.add_lag_members(parent_port, self.LAG_MEMBERS_UNDER_TEST)
            self.asic_db.wait_for_n_keys(ASIC_LAG_MEMBER_TABLE, len(self.LAG_MEMBERS_UNDER_TEST))
        if vrf_name:
            self.create_vrf(vrf_name)
            vrf_oid = self.get_newly_created_oid(ASIC_VIRTUAL_ROUTER_TABLE, [vrf_oid])
        self.create_sub_port_intf_profile(sub_port_intf_name, vrf_name)

        # Verify that sub port interface state ok is pushed to STATE_DB by Intfmgrd
        fv_dict = {
            "state": "ok",
        }
        self.check_sub_port_intf_fvs(self.state_db, state_tbl_name, sub_port_intf_name, fv_dict)

        # Verify vrf name sub port interface bound to in STATE_DB INTERFACE_TABLE
        fv_dict = {
            "vrf": vrf_name if vrf_name else "",
        }
        self.check_sub_port_intf_fvs(self.state_db, STATE_INTERFACE_TABLE_NAME, sub_port_intf_name, fv_dict)

        # If bound to non-default vrf, verify sub port interface vrf binding in linux kernel,
        # and parent port not bound to vrf
        if vrf_name:
            self.check_sub_port_intf_vrf_bind_kernel(dvs, sub_port_intf_name, vrf_name)
            self.check_sub_port_intf_vrf_nobind_kernel(dvs, parent_port, vrf_name)

        # Verify that sub port interface configuration is synced to APPL_DB INTF_TABLE by Intfmgrd
        fv_dict = {
            ADMIN_STATUS: "up",
        }
        if vrf_name:
            fv_dict[VRF_NAME if vrf_name.startswith(VRF_PREFIX) else VNET_NAME] = vrf_name
        self.check_sub_port_intf_fvs(self.app_db, APP_INTF_TABLE_NAME, sub_port_intf_name, fv_dict)

        # Verify that a sub port router interface entry is created in ASIC_DB
        fv_dict = {
            "SAI_ROUTER_INTERFACE_ATTR_TYPE": "SAI_ROUTER_INTERFACE_TYPE_SUB_PORT",
            "SAI_ROUTER_INTERFACE_ATTR_OUTER_VLAN_ID": "{}".format(vlan_id),
            "SAI_ROUTER_INTERFACE_ATTR_ADMIN_V4_STATE": "true",
            "SAI_ROUTER_INTERFACE_ATTR_ADMIN_V6_STATE": "true",
            "SAI_ROUTER_INTERFACE_ATTR_MTU": DEFAULT_MTU,
            "SAI_ROUTER_INTERFACE_ATTR_VIRTUAL_ROUTER_ID": vrf_oid,
        }
        rif_oid = self.get_newly_created_oid(ASIC_RIF_TABLE, old_rif_oids)
        self.check_sub_port_intf_fvs(self.asic_db, ASIC_RIF_TABLE, rif_oid, fv_dict)

        # Verify physical port host interface vlan tag attribute
        fv_dict = {
            "SAI_HOSTIF_ATTR_VLAN_TAG": "SAI_HOSTIF_VLAN_TAG_KEEP",
        }
        for phy_port in phy_ports:
            hostif_oid = dvs.asicdb.hostifnamemap[phy_port]
            self.check_sub_port_intf_fvs(self.asic_db, ASIC_HOSTIF_TABLE, hostif_oid, fv_dict)

        # Remove a sub port interface
        self.remove_sub_port_intf_profile(sub_port_intf_name)
        self.check_sub_port_intf_profile_removal(rif_oid)

        # Remove lag members from lag parent port
        if parent_port.startswith(LAG_PREFIX):
            self.remove_lag_members(parent_port, self.LAG_MEMBERS_UNDER_TEST)
            self.asic_db.wait_for_n_keys(ASIC_LAG_MEMBER_TABLE, 0)

        # Remove vrf if created
        if vrf_name:
            self.remove_vrf(vrf_name)
            self.check_vrf_removal(vrf_oid)
            if vrf_name.startswith(VNET_PREFIX):
                self.remove_vxlan_tunnel(self.TUNNEL_UNDER_TEST)
                self.app_db.wait_for_n_keys(ASIC_TUNNEL_TABLE, 0)

    def test_sub_port_intf_creation(self, dvs):
        self.connect_dbs(dvs)

        self._test_sub_port_intf_creation(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST)
        self._test_sub_port_intf_creation(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST)

        self._test_sub_port_intf_creation(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST, self.VRF_UNDER_TEST)
        self._test_sub_port_intf_creation(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST, self.VRF_UNDER_TEST)

        self._test_sub_port_intf_creation(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST, self.VNET_UNDER_TEST)
        self._test_sub_port_intf_creation(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST, self.VNET_UNDER_TEST)

    def _test_sub_port_intf_add_ip_addrs(self, dvs, sub_port_intf_name, vrf_name=None):
        substrs = sub_port_intf_name.split(VLAN_SUB_INTERFACE_SEPARATOR)
        parent_port = substrs[0]

        vrf_oid = self.default_vrf_oid
        old_rif_oids = self.get_oids(ASIC_RIF_TABLE)

        self.set_parent_port_admin_status(dvs, parent_port, "up")
        if vrf_name:
            self.create_vrf(vrf_name)
            vrf_oid = self.get_newly_created_oid(ASIC_VIRTUAL_ROUTER_TABLE, [vrf_oid])
        self.create_sub_port_intf_profile(sub_port_intf_name, vrf_name)

        self.add_sub_port_intf_ip_addr(sub_port_intf_name, self.IPV4_ADDR_UNDER_TEST)
        if vrf_name is None or not vrf_name.startswith(VNET_PREFIX):
            self.add_sub_port_intf_ip_addr(sub_port_intf_name, self.IPV6_ADDR_UNDER_TEST)

        rif_oid = self.get_newly_created_oid(ASIC_RIF_TABLE, old_rif_oids)

        # Verify that ip address state ok is pushed to STATE_DB INTERFACE_TABLE by Intfmgrd
        fv_dict = {
            "state": "ok",
        }
        self.check_sub_port_intf_fvs(self.state_db, STATE_INTERFACE_TABLE_NAME,
                                     sub_port_intf_name + "|" + self.IPV4_ADDR_UNDER_TEST, fv_dict)
        if vrf_name is None or not vrf_name.startswith(VNET_PREFIX):
            self.check_sub_port_intf_fvs(self.state_db, STATE_INTERFACE_TABLE_NAME,
                                         sub_port_intf_name + "|" + self.IPV6_ADDR_UNDER_TEST, fv_dict)

        # Verify that ip address configuration is synced to APPL_DB INTF_TABLE by Intfmgrd
        fv_dict = {
            "scope": "global",
            "family": "IPv4",
        }
        self.check_sub_port_intf_fvs(self.app_db, APP_INTF_TABLE_NAME,
                                     sub_port_intf_name + ":" + self.IPV4_ADDR_UNDER_TEST, fv_dict)
        if vrf_name is None or not vrf_name.startswith(VNET_PREFIX):
            fv_dict["family"] = "IPv6"
            self.check_sub_port_intf_fvs(self.app_db, APP_INTF_TABLE_NAME,
                                         sub_port_intf_name + ":" + self.IPV6_ADDR_UNDER_TEST, fv_dict)

        # Verify that an IPv4 ip2me route entry is created in ASIC_DB
        # Verify that an IPv4 subnet route entry is created in ASIC_DB
        # Verify that an IPv6 ip2me route entry is created in ASIC_DB for non-vnet case
        # Verify that an IPv6 subnet route entry is created in ASIC_DB for non-vnet case
        self.check_sub_port_intf_route_entries(vrf_oid, check_ipv6=True if vrf_name is None or not vrf_name.startswith(VNET_PREFIX) else False)

        # Remove IP addresses
        ip_addrs = [
            self.IPV4_ADDR_UNDER_TEST,
        ]
        self.remove_sub_port_intf_ip_addr(sub_port_intf_name, self.IPV4_ADDR_UNDER_TEST)
        if vrf_name is None or not vrf_name.startswith(VNET_PREFIX):
            ip_addrs.append(self.IPV6_ADDR_UNDER_TEST)
            self.remove_sub_port_intf_ip_addr(sub_port_intf_name, self.IPV6_ADDR_UNDER_TEST)
        self.check_sub_port_intf_ip_addr_removal(sub_port_intf_name, ip_addrs)

        # Remove a sub port interface
        self.remove_sub_port_intf_profile(sub_port_intf_name)
        self.check_sub_port_intf_profile_removal(rif_oid)

        # Remove vrf if created
        if vrf_name:
            self.remove_vrf(vrf_name)
            self.check_vrf_removal(vrf_oid)
            if vrf_name.startswith(VNET_PREFIX):
                self.remove_vxlan_tunnel(self.TUNNEL_UNDER_TEST)
                self.app_db.wait_for_n_keys(ASIC_TUNNEL_TABLE, 0)

    def test_sub_port_intf_add_ip_addrs(self, dvs):
        self.connect_dbs(dvs)

        self._test_sub_port_intf_add_ip_addrs(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST)
        self._test_sub_port_intf_add_ip_addrs(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST)

        self._test_sub_port_intf_add_ip_addrs(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST, self.VRF_UNDER_TEST)
        self._test_sub_port_intf_add_ip_addrs(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST, self.VRF_UNDER_TEST)

        self._test_sub_port_intf_add_ip_addrs(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST, self.VNET_UNDER_TEST)
        self._test_sub_port_intf_add_ip_addrs(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST, self.VNET_UNDER_TEST)

    def _test_sub_port_intf_appl_db_proc_seq(self, dvs, sub_port_intf_name, admin_up, vrf_name=None):
        substrs = sub_port_intf_name.split(VLAN_SUB_INTERFACE_SEPARATOR)
        parent_port = substrs[0]
        vlan_id = substrs[1]

        vrf_oid = self.default_vrf_oid
        old_rif_oids = self.get_oids(ASIC_RIF_TABLE)

        self.set_parent_port_admin_status(dvs, parent_port, "up")
        if vrf_name:
            self.create_vrf(vrf_name)
            vrf_oid = self.get_newly_created_oid(ASIC_VIRTUAL_ROUTER_TABLE, [vrf_oid])

        # Create ip address configuration in APPL_DB before creating configuration for sub port interface itself
        self.add_sub_port_intf_ip_addr_appl_db(sub_port_intf_name, self.IPV4_ADDR_UNDER_TEST)
        if vrf_name is None or not vrf_name.startswith(VNET_PREFIX):
            self.add_sub_port_intf_ip_addr_appl_db(sub_port_intf_name, self.IPV6_ADDR_UNDER_TEST)
        time.sleep(2)

        # Create sub port interface configuration in APPL_DB
        self.create_sub_port_intf_profile_appl_db(sub_port_intf_name, "up" if admin_up == True else "down", vrf_name)

        # Verify that a sub port router interface entry is created in ASIC_DB
        fv_dict = {
            "SAI_ROUTER_INTERFACE_ATTR_TYPE": "SAI_ROUTER_INTERFACE_TYPE_SUB_PORT",
            "SAI_ROUTER_INTERFACE_ATTR_OUTER_VLAN_ID": "{}".format(vlan_id),
            "SAI_ROUTER_INTERFACE_ATTR_ADMIN_V4_STATE": "true" if admin_up == True else "false",
            "SAI_ROUTER_INTERFACE_ATTR_ADMIN_V6_STATE": "true" if admin_up == True else "false",
            "SAI_ROUTER_INTERFACE_ATTR_MTU": DEFAULT_MTU,
            "SAI_ROUTER_INTERFACE_ATTR_VIRTUAL_ROUTER_ID": vrf_oid,
        }
        rif_oid = self.get_newly_created_oid(ASIC_RIF_TABLE, old_rif_oids)
        self.check_sub_port_intf_fvs(self.asic_db, ASIC_RIF_TABLE, rif_oid, fv_dict)

        # Remove ip addresses from APPL_DB
        self.remove_sub_port_intf_ip_addr_appl_db(sub_port_intf_name, self.IPV4_ADDR_UNDER_TEST)
        if vrf_name is None or not vrf_name.startswith(VNET_PREFIX):
            self.remove_sub_port_intf_ip_addr_appl_db(sub_port_intf_name, self.IPV6_ADDR_UNDER_TEST)
        # Remove sub port interface from APPL_DB
        self.remove_sub_port_intf_profile_appl_db(sub_port_intf_name)
        self.check_sub_port_intf_profile_removal(rif_oid)

        # Remove vrf if created
        if vrf_name:
            self.remove_vrf(vrf_name)
            self.check_vrf_removal(vrf_oid)
            if vrf_name.startswith(VNET_PREFIX):
                self.remove_vxlan_tunnel(self.TUNNEL_UNDER_TEST)
                self.app_db.wait_for_n_keys(ASIC_TUNNEL_TABLE, 0)

    def test_sub_port_intf_appl_db_proc_seq(self, dvs):
        self.connect_dbs(dvs)

        self._test_sub_port_intf_appl_db_proc_seq(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST, admin_up=True)
        self._test_sub_port_intf_appl_db_proc_seq(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST, admin_up=False)

        self._test_sub_port_intf_appl_db_proc_seq(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST, admin_up=True)
        self._test_sub_port_intf_appl_db_proc_seq(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST, admin_up=False)

        self._test_sub_port_intf_appl_db_proc_seq(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST, admin_up=True, vrf_name=self.VRF_UNDER_TEST)
        self._test_sub_port_intf_appl_db_proc_seq(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST, admin_up=False, vrf_name=self.VRF_UNDER_TEST)

        self._test_sub_port_intf_appl_db_proc_seq(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST, admin_up=True, vrf_name=self.VRF_UNDER_TEST)
        self._test_sub_port_intf_appl_db_proc_seq(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST, admin_up=False, vrf_name=self.VRF_UNDER_TEST)

        self._test_sub_port_intf_appl_db_proc_seq(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST, admin_up=True, vrf_name=self.VNET_UNDER_TEST)
        self._test_sub_port_intf_appl_db_proc_seq(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST, admin_up=False, vrf_name=self.VNET_UNDER_TEST)

        self._test_sub_port_intf_appl_db_proc_seq(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST, admin_up=True, vrf_name=self.VNET_UNDER_TEST)
        self._test_sub_port_intf_appl_db_proc_seq(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST, admin_up=False, vrf_name=self.VNET_UNDER_TEST)

    def _test_sub_port_intf_admin_status_change(self, dvs, sub_port_intf_name, vrf_name=None):
        substrs = sub_port_intf_name.split(VLAN_SUB_INTERFACE_SEPARATOR)
        parent_port = substrs[0]

        vrf_oid = self.default_vrf_oid
        old_rif_oids = self.get_oids(ASIC_RIF_TABLE)

        self.set_parent_port_admin_status(dvs, parent_port, "up")
        if vrf_name:
            self.create_vrf(vrf_name)
            vrf_oid = self.get_newly_created_oid(ASIC_VIRTUAL_ROUTER_TABLE, [vrf_oid])
        self.create_sub_port_intf_profile(sub_port_intf_name, vrf_name)

        self.add_sub_port_intf_ip_addr(sub_port_intf_name, self.IPV4_ADDR_UNDER_TEST)
        if vrf_name is None or not vrf_name.startswith(VNET_PREFIX):
            self.add_sub_port_intf_ip_addr(sub_port_intf_name, self.IPV6_ADDR_UNDER_TEST)

        # Verify sub port interface admin status in linux kernel
        self.check_sub_port_intf_admin_status_kernel(dvs, sub_port_intf_name, admin_up=True)

        fv_dict = {
            ADMIN_STATUS: "up",
        }
        if vrf_name:
            fv_dict[VRF_NAME if vrf_name.startswith(VRF_PREFIX) else VNET_NAME] = vrf_name
        self.check_sub_port_intf_fvs(self.app_db, APP_INTF_TABLE_NAME, sub_port_intf_name, fv_dict)

        fv_dict = {
            "SAI_ROUTER_INTERFACE_ATTR_ADMIN_V4_STATE": "true",
            "SAI_ROUTER_INTERFACE_ATTR_ADMIN_V6_STATE": "true",
            "SAI_ROUTER_INTERFACE_ATTR_MTU": DEFAULT_MTU,
            "SAI_ROUTER_INTERFACE_ATTR_VIRTUAL_ROUTER_ID": vrf_oid,
        }
        rif_oid = self.get_newly_created_oid(ASIC_RIF_TABLE, old_rif_oids)
        self.check_sub_port_intf_fvs(self.asic_db, ASIC_RIF_TABLE, rif_oid, fv_dict)

        # Change sub port interface admin status to down
        self.set_sub_port_intf_admin_status(sub_port_intf_name, "down")

        # Verify sub port interface admin status change in linux kernel
        self.check_sub_port_intf_admin_status_kernel(dvs, sub_port_intf_name, admin_up=False)

        # Verify that sub port interface admin status change is synced to APP_DB by Intfmgrd
        fv_dict = {
            ADMIN_STATUS: "down",
        }
        if vrf_name:
            fv_dict[VRF_NAME if vrf_name.startswith(VRF_PREFIX) else VNET_NAME] = vrf_name
        self.check_sub_port_intf_fvs(self.app_db, APP_INTF_TABLE_NAME, sub_port_intf_name, fv_dict)

        # Verify that sub port router interface entry in ASIC_DB has the updated admin status
        fv_dict = {
            "SAI_ROUTER_INTERFACE_ATTR_ADMIN_V4_STATE": "false",
            "SAI_ROUTER_INTERFACE_ATTR_ADMIN_V6_STATE": "false",
            "SAI_ROUTER_INTERFACE_ATTR_MTU": DEFAULT_MTU,
            "SAI_ROUTER_INTERFACE_ATTR_VIRTUAL_ROUTER_ID": vrf_oid,
        }
        rif_oid = self.get_newly_created_oid(ASIC_RIF_TABLE, old_rif_oids)
        self.check_sub_port_intf_fvs(self.asic_db, ASIC_RIF_TABLE, rif_oid, fv_dict)

        # Change sub port interface admin status to up
        self.set_sub_port_intf_admin_status(sub_port_intf_name, "up")

        # Verify sub port interface admin status change in linux kernel
        self.check_sub_port_intf_admin_status_kernel(dvs, sub_port_intf_name, admin_up=True)

        # Verify that sub port interface admin status change is synced to APP_DB by Intfmgrd
        fv_dict = {
            ADMIN_STATUS: "up",
        }
        if vrf_name:
            fv_dict[VRF_NAME if vrf_name.startswith(VRF_PREFIX) else VNET_NAME] = vrf_name
        self.check_sub_port_intf_fvs(self.app_db, APP_INTF_TABLE_NAME, sub_port_intf_name, fv_dict)

        # Verify that sub port router interface entry in ASIC_DB has the updated admin status
        fv_dict = {
            "SAI_ROUTER_INTERFACE_ATTR_ADMIN_V4_STATE": "true",
            "SAI_ROUTER_INTERFACE_ATTR_ADMIN_V6_STATE": "true",
            "SAI_ROUTER_INTERFACE_ATTR_MTU": DEFAULT_MTU,
            "SAI_ROUTER_INTERFACE_ATTR_VIRTUAL_ROUTER_ID": vrf_oid,
        }
        rif_oid = self.get_newly_created_oid(ASIC_RIF_TABLE, old_rif_oids)
        self.check_sub_port_intf_fvs(self.asic_db, ASIC_RIF_TABLE, rif_oid, fv_dict)

        # Remove IP addresses
        ip_addrs = [
            self.IPV4_ADDR_UNDER_TEST,
        ]
        self.remove_sub_port_intf_ip_addr(sub_port_intf_name, self.IPV4_ADDR_UNDER_TEST)
        if vrf_name is None or not vrf_name.startswith(VNET_PREFIX):
            ip_addrs.append(self.IPV6_ADDR_UNDER_TEST)
            self.remove_sub_port_intf_ip_addr(sub_port_intf_name, self.IPV6_ADDR_UNDER_TEST)
        self.check_sub_port_intf_ip_addr_removal(sub_port_intf_name, ip_addrs)

        # Remove a sub port interface
        self.remove_sub_port_intf_profile(sub_port_intf_name)
        self.check_sub_port_intf_profile_removal(rif_oid)

        # Remove vrf if created
        if vrf_name:
            self.remove_vrf(vrf_name)
            self.check_vrf_removal(vrf_oid)
            if vrf_name.startswith(VNET_PREFIX):
                self.remove_vxlan_tunnel(self.TUNNEL_UNDER_TEST)
                self.app_db.wait_for_n_keys(ASIC_TUNNEL_TABLE, 0)

    def test_sub_port_intf_admin_status_change(self, dvs):
        self.connect_dbs(dvs)

        self._test_sub_port_intf_admin_status_change(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST)
        self._test_sub_port_intf_admin_status_change(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST)

        self._test_sub_port_intf_admin_status_change(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST, self.VRF_UNDER_TEST)
        self._test_sub_port_intf_admin_status_change(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST, self.VRF_UNDER_TEST)

        self._test_sub_port_intf_admin_status_change(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST, self.VNET_UNDER_TEST)
        self._test_sub_port_intf_admin_status_change(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST, self.VNET_UNDER_TEST)

    def _test_sub_port_intf_parent_port_admin_status_change(self, dvs, sub_port_intf_name, vrf_name=None):
        substrs = sub_port_intf_name.split(VLAN_SUB_INTERFACE_SEPARATOR)
        parent_port = substrs[0]

        vrf_oid = self.default_vrf_oid
        old_rif_oids = self.get_oids(ASIC_RIF_TABLE)

        # Set parent port admin status up
        self.set_parent_port_admin_status(dvs, parent_port, "up")
        if vrf_name:
            self.create_vrf(vrf_name)
            vrf_oid = self.get_newly_created_oid(ASIC_VIRTUAL_ROUTER_TABLE, [vrf_oid])
        self.create_sub_port_intf_profile(sub_port_intf_name, vrf_name)

        self.add_sub_port_intf_ip_addr(sub_port_intf_name, self.IPV4_ADDR_UNDER_TEST)
        if vrf_name is None or not vrf_name.startswith(VNET_PREFIX):
            self.add_sub_port_intf_ip_addr(sub_port_intf_name, self.IPV6_ADDR_UNDER_TEST)

        # Verify sub port interface admin status up in linux kernel
        self.check_sub_port_intf_admin_status_kernel(dvs, sub_port_intf_name, admin_up=True)
        # Verify sub port interface admin status up in APP_DB
        fv_dict = {
            ADMIN_STATUS: "up",
        }
        if vrf_name:
            fv_dict[VRF_NAME if vrf_name.startswith(VRF_PREFIX) else VNET_NAME] = vrf_name
        self.check_sub_port_intf_fvs(self.app_db, APP_INTF_TABLE_NAME, sub_port_intf_name, fv_dict)
        # Verify sub port interface admin status up in ASIC_DB
        fv_dict = {
            "SAI_ROUTER_INTERFACE_ATTR_ADMIN_V4_STATE": "true",
            "SAI_ROUTER_INTERFACE_ATTR_ADMIN_V6_STATE": "true",
            "SAI_ROUTER_INTERFACE_ATTR_MTU": DEFAULT_MTU,
            "SAI_ROUTER_INTERFACE_ATTR_VIRTUAL_ROUTER_ID": vrf_oid,
        }
        rif_oid = self.get_newly_created_oid(ASIC_RIF_TABLE, old_rif_oids)
        self.check_sub_port_intf_fvs(self.asic_db, ASIC_RIF_TABLE, rif_oid, fv_dict)

        # Set parent port admin status down, with sub port interface admin status up
        self.set_parent_port_admin_status(dvs, parent_port, "down")

        # Verify sub port interface admin status down in linux kernel
        self.check_sub_port_intf_admin_status_kernel(dvs, sub_port_intf_name, admin_up=False)
        # Verify that sub port interface admin status in APP_DB stays unchanged (admin status up)
        fv_dict = {
            ADMIN_STATUS: "up",
        }
        if vrf_name:
            fv_dict[VRF_NAME if vrf_name.startswith(VRF_PREFIX) else VNET_NAME] = vrf_name
        self.check_sub_port_intf_fvs(self.app_db, APP_INTF_TABLE_NAME, sub_port_intf_name, fv_dict)
        # Verify that sub port router interface entry in ASIC_DB stays unchanged (admin status up)
        fv_dict = {
            "SAI_ROUTER_INTERFACE_ATTR_ADMIN_V4_STATE": "true",
            "SAI_ROUTER_INTERFACE_ATTR_ADMIN_V6_STATE": "true",
            "SAI_ROUTER_INTERFACE_ATTR_MTU": DEFAULT_MTU,
            "SAI_ROUTER_INTERFACE_ATTR_VIRTUAL_ROUTER_ID": vrf_oid,
        }
        rif_oid = self.get_newly_created_oid(ASIC_RIF_TABLE, old_rif_oids)
        self.check_sub_port_intf_fvs(self.asic_db, ASIC_RIF_TABLE, rif_oid, fv_dict)

        # Set parent port admin status up, with sub port interface admin status up
        self.set_parent_port_admin_status(dvs, parent_port, "up")

        # Verify sub port interface admin status up in linux kernel
        self.check_sub_port_intf_admin_status_kernel(dvs, sub_port_intf_name, admin_up=True)
        # Verify that sub port interface admin status in APP_DB stays unchanged (admin status up)
        fv_dict = {
            ADMIN_STATUS: "up",
        }
        if vrf_name:
            fv_dict[VRF_NAME if vrf_name.startswith(VRF_PREFIX) else VNET_NAME] = vrf_name
        self.check_sub_port_intf_fvs(self.app_db, APP_INTF_TABLE_NAME, sub_port_intf_name, fv_dict)
        # Verify that sub port router interface entry in ASIC_DB stays unchanged (admin status up)
        fv_dict = {
            "SAI_ROUTER_INTERFACE_ATTR_ADMIN_V4_STATE": "true",
            "SAI_ROUTER_INTERFACE_ATTR_ADMIN_V6_STATE": "true",
            "SAI_ROUTER_INTERFACE_ATTR_MTU": DEFAULT_MTU,
            "SAI_ROUTER_INTERFACE_ATTR_VIRTUAL_ROUTER_ID": vrf_oid,
        }
        rif_oid = self.get_newly_created_oid(ASIC_RIF_TABLE, old_rif_oids)
        self.check_sub_port_intf_fvs(self.asic_db, ASIC_RIF_TABLE, rif_oid, fv_dict)

        # Change sub port interface admin status to down, with parent port admin status up
        self.set_sub_port_intf_admin_status(sub_port_intf_name, "down")

        # Verify sub port interface admin status change in linux kernel
        self.check_sub_port_intf_admin_status_kernel(dvs, sub_port_intf_name, admin_up=False)
        # Verify that sub port interface admin status change is synced to APP_DB by Intfmgrd
        fv_dict = {
            ADMIN_STATUS: "down",
        }
        if vrf_name:
            fv_dict[VRF_NAME if vrf_name.startswith(VRF_PREFIX) else VNET_NAME] = vrf_name
        self.check_sub_port_intf_fvs(self.app_db, APP_INTF_TABLE_NAME, sub_port_intf_name, fv_dict)
        # Verify that sub port router interface entry in ASIC_DB has the updated admin status
        fv_dict = {
            "SAI_ROUTER_INTERFACE_ATTR_ADMIN_V4_STATE": "false",
            "SAI_ROUTER_INTERFACE_ATTR_ADMIN_V6_STATE": "false",
            "SAI_ROUTER_INTERFACE_ATTR_MTU": DEFAULT_MTU,
            "SAI_ROUTER_INTERFACE_ATTR_VIRTUAL_ROUTER_ID": vrf_oid,
        }
        rif_oid = self.get_newly_created_oid(ASIC_RIF_TABLE, old_rif_oids)
        self.check_sub_port_intf_fvs(self.asic_db, ASIC_RIF_TABLE, rif_oid, fv_dict)

        # Set parent port admin status down, with sub port interface admin status down
        self.set_parent_port_admin_status(dvs, parent_port, "down")

        # Verify sub port interface admin status down in linux kernel
        self.check_sub_port_intf_admin_status_kernel(dvs, sub_port_intf_name, admin_up=False)
        # Verify that sub port interface admin status in APP_DB stays unchanged (admin down)
        fv_dict = {
            ADMIN_STATUS: "down",
        }
        if vrf_name:
            fv_dict[VRF_NAME if vrf_name.startswith(VRF_PREFIX) else VNET_NAME] = vrf_name
        self.check_sub_port_intf_fvs(self.app_db, APP_INTF_TABLE_NAME, sub_port_intf_name, fv_dict)
        # Verify that sub port router interface entry in ASIC_DB stays unchanged (admin down)
        fv_dict = {
            "SAI_ROUTER_INTERFACE_ATTR_ADMIN_V4_STATE": "false",
            "SAI_ROUTER_INTERFACE_ATTR_ADMIN_V6_STATE": "false",
            "SAI_ROUTER_INTERFACE_ATTR_MTU": DEFAULT_MTU,
            "SAI_ROUTER_INTERFACE_ATTR_VIRTUAL_ROUTER_ID": vrf_oid,
        }
        rif_oid = self.get_newly_created_oid(ASIC_RIF_TABLE, old_rif_oids)
        self.check_sub_port_intf_fvs(self.asic_db, ASIC_RIF_TABLE, rif_oid, fv_dict)

        # Set parent port admin status up, with sub port interface admin status down
        self.set_parent_port_admin_status(dvs, parent_port, "up")

        # Verify sub port interface admin status down in linux kernel
        self.check_sub_port_intf_admin_status_kernel(dvs, sub_port_intf_name, admin_up=False)
        # Verify that sub port interface admin status in APP_DB stays unchanged (admin status down)
        fv_dict = {
            ADMIN_STATUS: "down",
        }
        if vrf_name:
            fv_dict[VRF_NAME if vrf_name.startswith(VRF_PREFIX) else VNET_NAME] = vrf_name
        self.check_sub_port_intf_fvs(self.app_db, APP_INTF_TABLE_NAME, sub_port_intf_name, fv_dict)
        # Verify that sub port router interface entry in ASIC_DB stays unchanged (admin status down)
        fv_dict = {
            "SAI_ROUTER_INTERFACE_ATTR_ADMIN_V4_STATE": "false",
            "SAI_ROUTER_INTERFACE_ATTR_ADMIN_V6_STATE": "false",
            "SAI_ROUTER_INTERFACE_ATTR_MTU": DEFAULT_MTU,
            "SAI_ROUTER_INTERFACE_ATTR_VIRTUAL_ROUTER_ID": vrf_oid,
        }
        rif_oid = self.get_newly_created_oid(ASIC_RIF_TABLE, old_rif_oids)
        self.check_sub_port_intf_fvs(self.asic_db, ASIC_RIF_TABLE, rif_oid, fv_dict)

        # Remove IP addresses
        ip_addrs = [
            self.IPV4_ADDR_UNDER_TEST,
        ]
        self.remove_sub_port_intf_ip_addr(sub_port_intf_name, self.IPV4_ADDR_UNDER_TEST)
        if vrf_name is None or not vrf_name.startswith(VNET_PREFIX):
            ip_addrs.append(self.IPV6_ADDR_UNDER_TEST)
            self.remove_sub_port_intf_ip_addr(sub_port_intf_name, self.IPV6_ADDR_UNDER_TEST)
        self.check_sub_port_intf_ip_addr_removal(sub_port_intf_name, ip_addrs)

        # Remove a sub port interface
        self.remove_sub_port_intf_profile(sub_port_intf_name)
        self.check_sub_port_intf_profile_removal(rif_oid)

        # Remove vrf if created
        if vrf_name:
            self.remove_vrf(vrf_name)
            self.check_vrf_removal(vrf_oid)
            if vrf_name.startswith(VNET_PREFIX):
                self.remove_vxlan_tunnel(self.TUNNEL_UNDER_TEST)
                self.app_db.wait_for_n_keys(ASIC_TUNNEL_TABLE, 0)

    def test_sub_port_intf_parent_port_admin_status_change(self, dvs):
        self.connect_dbs(dvs)

        self._test_sub_port_intf_parent_port_admin_status_change(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST)
        self._test_sub_port_intf_parent_port_admin_status_change(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST)

        self._test_sub_port_intf_parent_port_admin_status_change(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST, self.VRF_UNDER_TEST)
        self._test_sub_port_intf_parent_port_admin_status_change(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST, self.VRF_UNDER_TEST)

        self._test_sub_port_intf_parent_port_admin_status_change(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST, self.VNET_UNDER_TEST)
        self._test_sub_port_intf_parent_port_admin_status_change(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST, self.VNET_UNDER_TEST)

    def _test_sub_port_intf_remove_ip_addrs(self, dvs, sub_port_intf_name, vrf_name=None):
        substrs = sub_port_intf_name.split(VLAN_SUB_INTERFACE_SEPARATOR)
        parent_port = substrs[0]

        old_rif_oids = self.get_oids(ASIC_RIF_TABLE)

        self.set_parent_port_admin_status(dvs, parent_port, "up")
        if vrf_name:
            self.create_vrf(vrf_name)
            self.asic_db.wait_for_n_keys(ASIC_VIRTUAL_ROUTER_TABLE, 2)
        self.create_sub_port_intf_profile(sub_port_intf_name, vrf_name)

        self.add_sub_port_intf_ip_addr(sub_port_intf_name, self.IPV4_ADDR_UNDER_TEST)
        if vrf_name is None or not vrf_name.startswith(VNET_PREFIX):
            self.add_sub_port_intf_ip_addr(sub_port_intf_name, self.IPV6_ADDR_UNDER_TEST)

        rif_oid = self.get_newly_created_oid(ASIC_RIF_TABLE, old_rif_oids)

        # Remove IPv4 address
        self.remove_sub_port_intf_ip_addr(sub_port_intf_name, self.IPV4_ADDR_UNDER_TEST)

        # Verify that IPv4 address state ok is removed from STATE_DB INTERFACE_TABLE by Intfmgrd
        self.check_sub_port_intf_key_removal(self.state_db, STATE_INTERFACE_TABLE_NAME,
                                             sub_port_intf_name + "|" + self.IPV4_ADDR_UNDER_TEST)

        # Verify that IPv4 address configuration is removed from APPL_DB INTF_TABLE by Intfmgrd
        self.check_sub_port_intf_key_removal(self.app_db, APP_INTF_TABLE_NAME,
                                             sub_port_intf_name + ":" + self.IPV4_ADDR_UNDER_TEST)

        # Verify that IPv4 subnet route entry is removed from ASIC_DB
        # Verify that IPv4 ip2me route entry is removed from ASIC_DB
        removed_route_entries = set([self.IPV4_TOME_UNDER_TEST, self.IPV4_SUBNET_UNDER_TEST])
        self.check_sub_port_intf_route_entries_removal(removed_route_entries)

        # Remove IPv6 address for non-vnet cases
        if vrf_name is None or not vrf_name.startswith(VNET_PREFIX):
            self.remove_sub_port_intf_ip_addr(sub_port_intf_name, self.IPV6_ADDR_UNDER_TEST)

            # Verify that IPv6 address state ok is removed from STATE_DB INTERFACE_TABLE by Intfmgrd
            self.check_sub_port_intf_key_removal(self.state_db, STATE_INTERFACE_TABLE_NAME,
                                                 sub_port_intf_name + "|" + self.IPV6_ADDR_UNDER_TEST)

            # Verify that IPv6 address configuration is removed from APPL_DB INTF_TABLE by Intfmgrd
            self.check_sub_port_intf_key_removal(self.app_db, APP_INTF_TABLE_NAME,
                                                 sub_port_intf_name + ":" + self.IPV6_ADDR_UNDER_TEST)

            # Verify that IPv6 subnet route entry is removed from ASIC_DB
            # Verify that IPv6 ip2me route entry is removed from ASIC_DB
            removed_route_entries.update([self.IPV6_TOME_UNDER_TEST, self.IPV6_SUBNET_UNDER_TEST])
            self.check_sub_port_intf_route_entries_removal(removed_route_entries)

        # Verify that sub port router interface entry still exists in ASIC_DB
        self.check_sub_port_intf_key_existence(self.asic_db, ASIC_RIF_TABLE, rif_oid)

        # Remove a sub port interface
        self.remove_sub_port_intf_profile(sub_port_intf_name)
        self.check_sub_port_intf_profile_removal(rif_oid)

        # Remove vrf if created
        if vrf_name:
            self.remove_vrf(vrf_name)
            self.asic_db.wait_for_n_keys(ASIC_VIRTUAL_ROUTER_TABLE, 1)
            if vrf_name.startswith(VNET_PREFIX):
                self.remove_vxlan_tunnel(self.TUNNEL_UNDER_TEST)
                self.app_db.wait_for_n_keys(ASIC_TUNNEL_TABLE, 0)

    def test_sub_port_intf_remove_ip_addrs(self, dvs):
        self.connect_dbs(dvs)

        self._test_sub_port_intf_remove_ip_addrs(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST)
        self._test_sub_port_intf_remove_ip_addrs(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST)

        self._test_sub_port_intf_remove_ip_addrs(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST, self.VRF_UNDER_TEST)
        self._test_sub_port_intf_remove_ip_addrs(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST, self.VRF_UNDER_TEST)

        self._test_sub_port_intf_remove_ip_addrs(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST, self.VNET_UNDER_TEST)
        self._test_sub_port_intf_remove_ip_addrs(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST, self.VNET_UNDER_TEST)

    def _test_sub_port_intf_removal(self, dvs, sub_port_intf_name, vrf_name=None):
        substrs = sub_port_intf_name.split(VLAN_SUB_INTERFACE_SEPARATOR)
        parent_port = substrs[0]
        if parent_port.startswith(ETHERNET_PREFIX):
            state_tbl_name = STATE_PORT_TABLE_NAME
            phy_ports = [parent_port]
        else:
            assert parent_port.startswith(LAG_PREFIX)
            state_tbl_name = STATE_LAG_TABLE_NAME
            phy_ports = self.LAG_MEMBERS_UNDER_TEST

        old_rif_oids = self.get_oids(ASIC_RIF_TABLE)

        self.set_parent_port_admin_status(dvs, parent_port, "up")
        # Add lag members to test physical port host interface vlan tag attribute
        if parent_port.startswith(LAG_PREFIX):
            self.add_lag_members(parent_port, self.LAG_MEMBERS_UNDER_TEST)
            self.asic_db.wait_for_n_keys(ASIC_LAG_MEMBER_TABLE, len(self.LAG_MEMBERS_UNDER_TEST))
        if vrf_name:
            self.create_vrf(vrf_name)
            self.asic_db.wait_for_n_keys(ASIC_VIRTUAL_ROUTER_TABLE, 2)
        self.create_sub_port_intf_profile(sub_port_intf_name, vrf_name)

        self.add_sub_port_intf_ip_addr(sub_port_intf_name, self.IPV4_ADDR_UNDER_TEST)
        if vrf_name is None or not vrf_name.startswith(VNET_PREFIX):
            self.add_sub_port_intf_ip_addr(sub_port_intf_name, self.IPV6_ADDR_UNDER_TEST)

        rif_oid = self.get_newly_created_oid(ASIC_RIF_TABLE, old_rif_oids)

        fv_dict = {
            "state": "ok",
        }
        self.check_sub_port_intf_fvs(self.state_db, state_tbl_name, sub_port_intf_name, fv_dict)

        fv_dict = {
            "vrf": vrf_name if vrf_name else "",
        }
        self.check_sub_port_intf_fvs(self.state_db, STATE_INTERFACE_TABLE_NAME, sub_port_intf_name, fv_dict)

        if vrf_name:
            self.check_sub_port_intf_vrf_bind_kernel(dvs, sub_port_intf_name, vrf_name)
            self.check_sub_port_intf_vrf_nobind_kernel(dvs, parent_port, vrf_name)

        fv_dict = {
            ADMIN_STATUS: "up",
        }
        if vrf_name:
            fv_dict[VRF_NAME if vrf_name.startswith(VRF_PREFIX) else VNET_NAME] = vrf_name
        self.check_sub_port_intf_fvs(self.app_db, APP_INTF_TABLE_NAME, sub_port_intf_name, fv_dict)

        # Remove IP addresses
        ip_addrs = [
            self.IPV4_ADDR_UNDER_TEST,
        ]
        self.remove_sub_port_intf_ip_addr(sub_port_intf_name, self.IPV4_ADDR_UNDER_TEST)
        if vrf_name is None or not vrf_name.startswith(VNET_PREFIX):
            ip_addrs.append(self.IPV6_ADDR_UNDER_TEST)
            self.remove_sub_port_intf_ip_addr(sub_port_intf_name, self.IPV6_ADDR_UNDER_TEST)
        self.check_sub_port_intf_ip_addr_removal(sub_port_intf_name, ip_addrs)

        # Remove a sub port interface
        self.remove_sub_port_intf_profile(sub_port_intf_name)
        self.check_sub_port_intf_profile_removal(rif_oid)

        # Verify that sub port interface state ok is removed from STATE_DB by Intfmgrd
        self.check_sub_port_intf_key_removal(self.state_db, state_tbl_name, sub_port_intf_name)

        # Verify sub port interface not exist in linux kernel
        self.check_sub_port_intf_removal_kernel(dvs, sub_port_intf_name)
        # If bound to non-default vrf, verify parent port not bound to vrf
        if vrf_name:
            self.check_sub_port_intf_vrf_nobind_kernel(dvs, parent_port, vrf_name)

        # Verify vrf name sub port interface bound to is removed from STATE_DB INTERFACE_TABLE
        self.check_sub_port_intf_key_removal(self.state_db, STATE_INTERFACE_TABLE_NAME, sub_port_intf_name)

        # Verify that sub port interface configuration is removed from APP_DB by Intfmgrd
        self.check_sub_port_intf_key_removal(self.app_db, APP_INTF_TABLE_NAME, sub_port_intf_name)

        # Verify that sub port router interface entry is removed from ASIC_DB
        self.check_sub_port_intf_key_removal(self.asic_db, ASIC_RIF_TABLE, rif_oid)

        # Verify physical port host interface vlan tag attribute
        fv_dict = {
            "SAI_HOSTIF_ATTR_VLAN_TAG": "SAI_HOSTIF_VLAN_TAG_STRIP",
        }
        for phy_port in phy_ports:
            hostif_oid = dvs.asicdb.hostifnamemap[phy_port]
            self.check_sub_port_intf_fvs(self.asic_db, ASIC_HOSTIF_TABLE, hostif_oid, fv_dict)

        # Remove lag members from lag parent port
        if parent_port.startswith(LAG_PREFIX):
            self.remove_lag_members(parent_port, self.LAG_MEMBERS_UNDER_TEST)
            self.asic_db.wait_for_n_keys(ASIC_LAG_MEMBER_TABLE, 0)

        # Remove vrf if created
        if vrf_name:
            self.remove_vrf(vrf_name)
            self.asic_db.wait_for_n_keys(ASIC_VIRTUAL_ROUTER_TABLE, 1)
            if vrf_name.startswith(VNET_PREFIX):
                self.remove_vxlan_tunnel(self.TUNNEL_UNDER_TEST)
                self.app_db.wait_for_n_keys(ASIC_TUNNEL_TABLE, 0)

    def test_sub_port_intf_removal(self, dvs):
        self.connect_dbs(dvs)

        self._test_sub_port_intf_removal(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST)
        self._test_sub_port_intf_removal(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST)

        self._test_sub_port_intf_removal(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST, self.VRF_UNDER_TEST)
        self._test_sub_port_intf_removal(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST, self.VRF_UNDER_TEST)

        self._test_sub_port_intf_removal(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST, self.VNET_UNDER_TEST)
        self._test_sub_port_intf_removal(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST, self.VNET_UNDER_TEST)

    def _test_sub_port_intf_mtu(self, dvs, sub_port_intf_name, vrf_name=None):
        substrs = sub_port_intf_name.split(VLAN_SUB_INTERFACE_SEPARATOR)
        parent_port = substrs[0]

        vrf_oid = self.default_vrf_oid
        old_rif_oids = self.get_oids(ASIC_RIF_TABLE)

        self.set_parent_port_admin_status(dvs, parent_port, "up")
        if vrf_name:
            self.create_vrf(vrf_name)
            vrf_oid = self.get_newly_created_oid(ASIC_VIRTUAL_ROUTER_TABLE, [vrf_oid])
        self.create_sub_port_intf_profile(sub_port_intf_name, vrf_name)

        rif_oid = self.get_newly_created_oid(ASIC_RIF_TABLE, old_rif_oids)

        # Verify sub port interface mtu in linux kernel
        self.check_sub_port_intf_mtu_kernel(dvs, sub_port_intf_name, DEFAULT_MTU)

        # Change parent port mtu
        mtu = "8888"
        dvs.set_mtu(parent_port, mtu)

        # Verify sub port interface mtu in linux kernel
        self.check_sub_port_intf_mtu_kernel(dvs, sub_port_intf_name, mtu)

        # Verify that sub port router interface entry in ASIC_DB has the updated mtu
        fv_dict = {
            "SAI_ROUTER_INTERFACE_ATTR_MTU": mtu,
            "SAI_ROUTER_INTERFACE_ATTR_VIRTUAL_ROUTER_ID": vrf_oid,
        }
        self.check_sub_port_intf_fvs(self.asic_db, ASIC_RIF_TABLE, rif_oid, fv_dict)

        # Change parent port mtu
        mtu = "6666"
        dvs.set_mtu(parent_port, mtu)

        # Verify sub port interface mtu in linux kernel
        self.check_sub_port_intf_mtu_kernel(dvs, sub_port_intf_name, mtu)

        # Verify that sub port router interface entry in ASIC_DB has the updated mtu
        fv_dict = {
            "SAI_ROUTER_INTERFACE_ATTR_MTU": mtu,
            "SAI_ROUTER_INTERFACE_ATTR_VIRTUAL_ROUTER_ID": vrf_oid,
        }
        self.check_sub_port_intf_fvs(self.asic_db, ASIC_RIF_TABLE, rif_oid, fv_dict)

        # Change parent port mtu
        mtu = "7777"
        dvs.set_mtu(parent_port, mtu)

        # Verify sub port interface mtu in linux kernel
        self.check_sub_port_intf_mtu_kernel(dvs, sub_port_intf_name, mtu)

        # Verify that sub port router interface entry in ASIC_DB has the updated mtu
        fv_dict = {
            "SAI_ROUTER_INTERFACE_ATTR_MTU": mtu,
            "SAI_ROUTER_INTERFACE_ATTR_VIRTUAL_ROUTER_ID": vrf_oid,
        }
        self.check_sub_port_intf_fvs(self.asic_db, ASIC_RIF_TABLE, rif_oid, fv_dict)

        # Restore parent port mtu
        dvs.set_mtu(parent_port, DEFAULT_MTU)

        # Verify sub port interface mtu in linux kernel
        self.check_sub_port_intf_mtu_kernel(dvs, sub_port_intf_name, DEFAULT_MTU)

        # Verify that sub port router interface entry in ASIC_DB has the default mtu
        fv_dict = {
            "SAI_ROUTER_INTERFACE_ATTR_MTU": DEFAULT_MTU,
            "SAI_ROUTER_INTERFACE_ATTR_VIRTUAL_ROUTER_ID": vrf_oid,
        }
        self.check_sub_port_intf_fvs(self.asic_db, ASIC_RIF_TABLE, rif_oid, fv_dict)

        # Remove a sub port interface
        self.remove_sub_port_intf_profile(sub_port_intf_name)
        self.check_sub_port_intf_profile_removal(rif_oid)

        # Remove vrf if created
        if vrf_name:
            self.remove_vrf(vrf_name)
            self.check_vrf_removal(vrf_oid)
            if vrf_name.startswith(VNET_PREFIX):
                self.remove_vxlan_tunnel(self.TUNNEL_UNDER_TEST)
                self.app_db.wait_for_n_keys(ASIC_TUNNEL_TABLE, 0)

    def test_sub_port_intf_mtu(self, dvs):
        self.connect_dbs(dvs)

        self._test_sub_port_intf_mtu(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST)
        self._test_sub_port_intf_mtu(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST)

        self._test_sub_port_intf_mtu(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST, self.VRF_UNDER_TEST)
        self._test_sub_port_intf_mtu(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST, self.VRF_UNDER_TEST)

        self._test_sub_port_intf_mtu(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST, self.VNET_UNDER_TEST)
        self._test_sub_port_intf_mtu(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST, self.VNET_UNDER_TEST)

    def create_nhg_router_intfs(self, dvs, parent_port_prefix, parent_port_idx_base, vlan_id, nhop_num, vrf_name=None):
        ifnames = []
        parent_port_idx = parent_port_idx_base
        for i in range(0, nhop_num):
            if vlan_id != 0:
                port_name = "{}{}.{}".format(parent_port_prefix, parent_port_idx, vlan_id)
            else:
                port_name = "{}{}".format(parent_port_prefix, parent_port_idx)
            ip_addr = "10.{}.{}.0/31".format(parent_port_idx, vlan_id)
            if vlan_id != 0:
                self.create_sub_port_intf_profile(port_name, vrf_name)
                self.add_sub_port_intf_ip_addr(port_name, ip_addr)
            else:
                dvs.add_ip_address(port_name, ip_addr, vrf_name)

            ifnames.append(port_name)

            parent_port_idx += (4 if parent_port_prefix == ETHERNET_PREFIX else 1)
        return ifnames

    def create_nhg_next_hop_objs(self, dvs, parent_port_prefix, parent_port_idx_base, vlan_id, nhop_num):
        nhop_ips = []
        parent_port_idx = parent_port_idx_base
        for i in range(0, nhop_num):
            if vlan_id != 0:
                port_name = "{}{}.{}".format(parent_port_prefix, parent_port_idx, vlan_id)
            else:
                port_name = "{}{}".format(parent_port_prefix, parent_port_idx)
            nhop_ip = "10.{}.{}.1".format(parent_port_idx, vlan_id)
            nhop_mac = "00:00:00:{:02d}:{}:01".format(parent_port_idx, vlan_id)
            dvs.runcmd("ip neigh add " + nhop_ip + " lladdr " + nhop_mac + " dev " + port_name)

            nhop_ips.append(nhop_ip)

            parent_port_idx += (4 if parent_port_prefix == ETHERNET_PREFIX else 1)
        return nhop_ips

    def remove_nhg_router_intfs(self, dvs, parent_port_prefix, parent_port_idx_base, vlan_id, nhop_num):
        parent_port_idx = parent_port_idx_base
        for i in range(0, nhop_num):
            if vlan_id != 0:
                port_name = "{}{}.{}".format(parent_port_prefix, parent_port_idx, vlan_id)
            else:
                port_name = "{}{}".format(parent_port_prefix, parent_port_idx)
            ip_addr = "10.{}.{}.0/31".format(parent_port_idx, vlan_id)
            if vlan_id != 0:
                # Remove IP address on sub port interface
                self.remove_sub_port_intf_ip_addr(port_name, ip_addr)
                # Remove sub port interface
                self.remove_sub_port_intf_profile(port_name)
            else:
                dvs.remove_ip_address(port_name, ip_addr)

            parent_port_idx += (4 if parent_port_prefix == ETHERNET_PREFIX else 1)

    def remove_nhg_next_hop_objs(self, dvs, parent_port_prefix, parent_port_idx_base, vlan_id, nhop_num):
        parent_port_idx = parent_port_idx_base
        for i in range(0, nhop_num):
            if vlan_id != 0:
                port_name = "{}{}.{}".format(parent_port_prefix, parent_port_idx, vlan_id)
            else:
                port_name = "{}{}".format(parent_port_prefix, parent_port_idx)
            nhop_ip = "10.{}.{}.1".format(parent_port_idx, vlan_id)
            dvs.runcmd("ip neigh del " + nhop_ip + " dev " + port_name)

            parent_port_idx += (4 if parent_port_prefix == ETHERNET_PREFIX else 1)

    def check_nhg_members_on_parent_port_oper_status_change(self, dvs, parent_port_prefix, parent_port_idx_base, status,
                                                            nhg_oid, nhop_num, create_intf_on_parent_port):
        parent_port_idx = parent_port_idx_base
        for i in range(0, nhop_num):
            port_name = "{}{}".format(parent_port_prefix, parent_port_idx)
            self.set_parent_port_oper_status(dvs, port_name, status)

            # Verify parent port oper status
            fv_dict = {
                "oper_status" : status,
            }
            if parent_port_prefix == ETHERNET_PREFIX:
                self.check_sub_port_intf_fvs(self.app_db, APP_PORT_TABLE_NAME, port_name, fv_dict)
            else:
                self.check_sub_port_intf_fvs(self.app_db, APP_LAG_TABLE_NAME, port_name, fv_dict)

            # Verify next hop group member # in ASIC_DB
            if status == "up":
                nhg_member_oids = self.asic_db.wait_for_n_keys(ASIC_NEXT_HOP_GROUP_MEMBER_TABLE,
                                                               1 + i if create_intf_on_parent_port == False else (1 + i) * 2)
            else:
                assert status == "down"
                nhg_member_oids = self.asic_db.wait_for_n_keys(ASIC_NEXT_HOP_GROUP_MEMBER_TABLE,
                                                               (nhop_num - 1) - i if create_intf_on_parent_port == False else
                                                               ((nhop_num - 1) - i) * 2)

            # Verify that next hop group members in ASIC_DB all
            # belong to the next hop group of the specified oid
            fv_dict = {
                "SAI_NEXT_HOP_GROUP_MEMBER_ATTR_NEXT_HOP_GROUP_ID": nhg_oid,
            }
            for nhg_member_oid in nhg_member_oids:
                self.check_sub_port_intf_fvs(self.asic_db, ASIC_NEXT_HOP_GROUP_MEMBER_TABLE, nhg_member_oid, fv_dict)

            parent_port_idx += (4 if parent_port_prefix == ETHERNET_PREFIX else 1)

    def _test_sub_port_intf_nhg_accel(self, dvs, sub_port_intf_name, nhop_num=3, create_intf_on_parent_port=False, vrf_name=None):
        substrs = sub_port_intf_name.split(VLAN_SUB_INTERFACE_SEPARATOR)
        parent_port = substrs[0]
        vlan_id = substrs[1]
        assert len(vlan_id) == 2

        if parent_port.startswith(ETHERNET_PREFIX):
            parent_port_prefix = ETHERNET_PREFIX
        else:
            assert parent_port.startswith(LAG_PREFIX)
            parent_port_prefix = LAG_PREFIX
        parent_port_idx_base = self.get_parent_port_index(parent_port)

        vrf_oid = self.default_vrf_oid

        # Set parent ports admin status up
        parent_port_idx = parent_port_idx_base
        for i in range(0, nhop_num):
            port_name = "{}{}".format(parent_port_prefix, parent_port_idx)
            self.set_parent_port_admin_status(dvs, port_name, "up")

            parent_port_idx += (4 if parent_port_prefix == ETHERNET_PREFIX else 1)

        if vrf_name:
            self.create_vrf(vrf_name)
            vrf_oid = self.get_newly_created_oid(ASIC_VIRTUAL_ROUTER_TABLE, [vrf_oid])

        ifnames = []
        rif_cnt = len(self.asic_db.get_keys(ASIC_RIF_TABLE))
        # Create sub port interfaces
        ifnames.extend(self.create_nhg_router_intfs(dvs, parent_port_prefix, parent_port_idx_base, int(vlan_id), nhop_num, vrf_name))

        # Create router interfaces on parent ports
        if create_intf_on_parent_port == True:
            ifnames.extend(self.create_nhg_router_intfs(dvs, parent_port_prefix, parent_port_idx_base, 0, nhop_num, vrf_name))

        self.asic_db.wait_for_n_keys(ASIC_RIF_TABLE, rif_cnt + nhop_num if create_intf_on_parent_port == False else rif_cnt + nhop_num * 2)

        nhop_ips = []
        nhop_cnt = len(self.asic_db.get_keys(ASIC_NEXT_HOP_TABLE))
        # Create next hop objects on sub port interfaces
        nhop_ips.extend(self.create_nhg_next_hop_objs(dvs, parent_port_prefix, parent_port_idx_base, int(vlan_id), nhop_num))

        # Create next hop objects on router interfaces
        if create_intf_on_parent_port == True:
            nhop_ips.extend(self.create_nhg_next_hop_objs(dvs, parent_port_prefix, parent_port_idx_base, 0, nhop_num))

        self.asic_db.wait_for_n_keys(ASIC_NEXT_HOP_TABLE, nhop_cnt + nhop_num if create_intf_on_parent_port == False else nhop_cnt + nhop_num * 2)

        # Create multi-next-hop route entry
        rt_tbl = swsscommon.ProducerStateTable(self.app_db.db_connection, APP_ROUTE_TABLE_NAME)
        fvs = swsscommon.FieldValuePairs([("nexthop", ",".join(nhop_ips)), ("ifname", ",".join(ifnames))])
        ip_prefix = "2.2.2.0/24"
        rt_tbl.set(vrf_name + APPL_DB_SEPARATOR + ip_prefix if vrf_name else ip_prefix, fvs)

        # Verify route entry created in ASIC_DB and get next hop group oid
        nhg_oid = self.get_ip_prefix_nhg_oid(ip_prefix, vrf_oid)

        # Verify next hop group of the specified oid created in ASIC_DB
        self.check_sub_port_intf_key_existence(self.asic_db, ASIC_NEXT_HOP_GROUP_TABLE, nhg_oid)

        # Verify next hop group members created in ASIC_DB
        nhg_member_oids = self.asic_db.wait_for_n_keys(ASIC_NEXT_HOP_GROUP_MEMBER_TABLE,
                                                       nhop_num if create_intf_on_parent_port == False else nhop_num * 2)

        # Verify that next hop group members all belong to the next hop group of the specified oid
        fv_dict = {
            "SAI_NEXT_HOP_GROUP_MEMBER_ATTR_NEXT_HOP_GROUP_ID": nhg_oid,
        }
        for nhg_member_oid in nhg_member_oids:
            self.check_sub_port_intf_fvs(self.asic_db, ASIC_NEXT_HOP_GROUP_MEMBER_TABLE, nhg_member_oid, fv_dict)

        # Bring parent ports oper status down one at a time, and verify next hop group members
        self.check_nhg_members_on_parent_port_oper_status_change(dvs, parent_port_prefix, parent_port_idx_base, "down",
                                                                 nhg_oid, nhop_num, create_intf_on_parent_port)

        # Bring parent ports oper status up one at a time, and verify next hop group members
        self.check_nhg_members_on_parent_port_oper_status_change(dvs, parent_port_prefix, parent_port_idx_base, "up",
                                                                 nhg_oid, nhop_num, create_intf_on_parent_port)

        # Clean up
        rif_cnt = len(self.asic_db.get_keys(ASIC_RIF_TABLE))

        # Remove ecmp route entry
        rt_tbl._del(vrf_name + APPL_DB_SEPARATOR + ip_prefix if vrf_name else ip_prefix)

        # Remove sub port interfaces
        self.remove_nhg_router_intfs(dvs, parent_port_prefix, parent_port_idx_base, int(vlan_id), nhop_num)

        # Remove router interfaces on parent ports
        if create_intf_on_parent_port == True:
            self.remove_nhg_router_intfs(dvs, parent_port_prefix, parent_port_idx_base, 0, nhop_num)

        # Removal of router interfaces indicates the proper removal of nhg, nhg members, next hop objects, and neighbor entries
        self.asic_db.wait_for_n_keys(ASIC_RIF_TABLE, rif_cnt - nhop_num if create_intf_on_parent_port == False else rif_cnt - nhop_num * 2)

        # Remove vrf if created
        if vrf_name:
            self.remove_vrf(vrf_name)
            self.check_vrf_removal(vrf_oid)

        # Make sure parent port is oper status up
        parent_port_idx = parent_port_idx_base
        for i in range(0, nhop_num):
            port_name = "{}{}".format(parent_port_prefix, parent_port_idx)
            self.set_parent_port_oper_status(dvs, port_name, "up")

            parent_port_idx += (4 if parent_port_prefix == ETHERNET_PREFIX else 1)

    def test_sub_port_intf_nhg_accel(self, dvs):
        self.connect_dbs(dvs)

        self._test_sub_port_intf_nhg_accel(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST)
        self._test_sub_port_intf_nhg_accel(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST, create_intf_on_parent_port=True)
        self._test_sub_port_intf_nhg_accel(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST)
        self._test_sub_port_intf_nhg_accel(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST, create_intf_on_parent_port=True)

        self._test_sub_port_intf_nhg_accel(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST, vrf_name=self.VRF_UNDER_TEST)
        self._test_sub_port_intf_nhg_accel(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST,
                                           create_intf_on_parent_port=True, vrf_name=self.VRF_UNDER_TEST)
        self._test_sub_port_intf_nhg_accel(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST, vrf_name=self.VRF_UNDER_TEST)
        self._test_sub_port_intf_nhg_accel(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST,
                                           create_intf_on_parent_port=True, vrf_name=self.VRF_UNDER_TEST)

    def _test_sub_port_intf_oper_down_with_pending_neigh_route_tasks(self, dvs, sub_port_intf_name, nhop_num=3,
                                                                     create_intf_on_parent_port=False, vrf_name=None):
        substrs = sub_port_intf_name.split(VLAN_SUB_INTERFACE_SEPARATOR)
        parent_port = substrs[0]
        vlan_id = substrs[1]
        assert len(vlan_id) == 2

        if parent_port.startswith(ETHERNET_PREFIX):
            parent_port_prefix = ETHERNET_PREFIX
        else:
            assert parent_port.startswith(LAG_PREFIX)
            parent_port_prefix = LAG_PREFIX
        parent_port_idx_base = self.get_parent_port_index(parent_port)

        vrf_oid = self.default_vrf_oid

        # Set parent ports admin status up
        parent_port_idx = parent_port_idx_base
        for i in range(0, nhop_num):
            port_name = "{}{}".format(parent_port_prefix, parent_port_idx)
            self.set_parent_port_admin_status(dvs, port_name, "up")

            parent_port_idx += (4 if parent_port_prefix == ETHERNET_PREFIX else 1)

        if vrf_name:
            self.create_vrf(vrf_name)
            vrf_oid = self.get_newly_created_oid(ASIC_VIRTUAL_ROUTER_TABLE, [vrf_oid])

        ifnames = []
        rif_cnt = len(self.asic_db.get_keys(ASIC_RIF_TABLE))
        # Create sub port interfaces
        ifnames.extend(self.create_nhg_router_intfs(dvs, parent_port_prefix, parent_port_idx_base, int(vlan_id), nhop_num, vrf_name))
        # Create router interfaces on parent ports
        if create_intf_on_parent_port == True:
            ifnames.extend(self.create_nhg_router_intfs(dvs, parent_port_prefix, parent_port_idx_base, 0, nhop_num, vrf_name))
        self.asic_db.wait_for_n_keys(ASIC_RIF_TABLE, rif_cnt + nhop_num if create_intf_on_parent_port == False else rif_cnt + nhop_num * 2)

        # Bring parent port oper status down one at a time
        # Verify next hop group members created after processing pending tasks
        parent_port_idx = parent_port_idx_base
        for i in range(0, nhop_num):
            port_name = "{}{}".format(parent_port_prefix, parent_port_idx)
            self.set_parent_port_oper_status(dvs, port_name, "down")

            # Verify parent port oper status down
            fv_dict = {
                "oper_status" : "down",
            }
            if parent_port_prefix == ETHERNET_PREFIX:
                self.check_sub_port_intf_fvs(self.app_db, APP_PORT_TABLE_NAME, port_name, fv_dict)
            else:
                self.check_sub_port_intf_fvs(self.app_db, APP_LAG_TABLE_NAME, port_name, fv_dict)

            # Mimic pending neighbor task
            nhop_ips = []
            nhop_cnt = len(self.asic_db.get_keys(ASIC_NEXT_HOP_TABLE))
            # Create next hop objects on sub port interfaces
            nhop_ips.extend(self.create_nhg_next_hop_objs(dvs, parent_port_prefix, parent_port_idx_base, int(vlan_id), nhop_num))
            # Create next hop objects on router interfaces
            if create_intf_on_parent_port == True:
                nhop_ips.extend(self.create_nhg_next_hop_objs(dvs, parent_port_prefix, parent_port_idx_base, 0, nhop_num))
            self.asic_db.wait_for_n_keys(ASIC_NEXT_HOP_TABLE, nhop_cnt + nhop_num if create_intf_on_parent_port == False else nhop_cnt + nhop_num * 2)

            # Mimic pending multi-next-hop route entry task
            rt_tbl = swsscommon.ProducerStateTable(self.app_db.db_connection, APP_ROUTE_TABLE_NAME)
            fvs = swsscommon.FieldValuePairs([("nexthop", ",".join(nhop_ips)), ("ifname", ",".join(ifnames))])
            ip_prefix = "2.2.2.0/24"
            rt_tbl.set(vrf_name + APPL_DB_SEPARATOR + ip_prefix if vrf_name else ip_prefix, fvs)

            # Verify route entry created in ASIC_DB and get next hop group oid
            nhg_oid = self.get_ip_prefix_nhg_oid(ip_prefix, vrf_oid)

            # Verify next hop group of the specified oid created in ASIC_DB
            self.check_sub_port_intf_key_existence(self.asic_db, ASIC_NEXT_HOP_GROUP_TABLE, nhg_oid)

            # Verify next hop group member # created in ASIC_DB
            nhg_member_oids = self.asic_db.wait_for_n_keys(ASIC_NEXT_HOP_GROUP_MEMBER_TABLE,
                                                           (nhop_num - 1) - i if create_intf_on_parent_port == False else ((nhop_num - 1) - i) * 2)

            # Verify that next hop group members all belong to the next hop group of the specified oid
            fv_dict = {
                "SAI_NEXT_HOP_GROUP_MEMBER_ATTR_NEXT_HOP_GROUP_ID": nhg_oid,
            }
            for nhg_member_oid in nhg_member_oids:
                self.check_sub_port_intf_fvs(self.asic_db, ASIC_NEXT_HOP_GROUP_MEMBER_TABLE, nhg_member_oid, fv_dict)

            nhop_cnt = len(self.asic_db.get_keys(ASIC_NEXT_HOP_TABLE))
            # Remove next hop objects on sub port interfaces
            self.remove_nhg_next_hop_objs(dvs, parent_port_prefix, parent_port_idx_base, int(vlan_id), nhop_num)
            # Remove next hop objects on router interfaces
            if create_intf_on_parent_port == True:
                self.remove_nhg_next_hop_objs(dvs, parent_port_prefix, parent_port_idx_base, 0, nhop_num)
            # Remove ecmp route entry
            rt_tbl._del(vrf_name + APPL_DB_SEPARATOR + ip_prefix if vrf_name else ip_prefix)
            # Removal of next hop objects indicates the proper removal of route entry, nhg, and nhg members
            self.asic_db.wait_for_n_keys(ASIC_NEXT_HOP_TABLE, nhop_cnt - nhop_num if create_intf_on_parent_port == False else nhop_cnt - nhop_num * 2)

            parent_port_idx += (4 if parent_port_prefix == ETHERNET_PREFIX else 1)

        # Clean up
        rif_cnt = len(self.asic_db.get_keys(ASIC_RIF_TABLE))
        # Remove sub port interfaces
        self.remove_nhg_router_intfs(dvs, parent_port_prefix, parent_port_idx_base, int(vlan_id), nhop_num)
        # Remove router interfaces on parent ports
        if create_intf_on_parent_port == True:
            self.remove_nhg_router_intfs(dvs, parent_port_prefix, parent_port_idx_base, 0, nhop_num)
        self.asic_db.wait_for_n_keys(ASIC_RIF_TABLE, rif_cnt - nhop_num if create_intf_on_parent_port == False else rif_cnt - nhop_num * 2)

        # Remove vrf if created
        if vrf_name:
            self.remove_vrf(vrf_name)
            self.check_vrf_removal(vrf_oid)

        # Make sure parent port oper status is up
        parent_port_idx = parent_port_idx_base
        for i in range(0, nhop_num):
            port_name = "{}{}".format(parent_port_prefix, parent_port_idx)
            self.set_parent_port_oper_status(dvs, port_name, "up")

            parent_port_idx += (4 if parent_port_prefix == ETHERNET_PREFIX else 1)

    def test_sub_port_intf_oper_down_with_pending_neigh_route_tasks(self, dvs):
        self.connect_dbs(dvs)

        self._test_sub_port_intf_oper_down_with_pending_neigh_route_tasks(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST)
        self._test_sub_port_intf_oper_down_with_pending_neigh_route_tasks(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST, create_intf_on_parent_port=True)
        self._test_sub_port_intf_oper_down_with_pending_neigh_route_tasks(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST)
        self._test_sub_port_intf_oper_down_with_pending_neigh_route_tasks(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST, create_intf_on_parent_port=True)

        self._test_sub_port_intf_oper_down_with_pending_neigh_route_tasks(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST, vrf_name=self.VRF_UNDER_TEST)
        self._test_sub_port_intf_oper_down_with_pending_neigh_route_tasks(dvs, self.SUB_PORT_INTERFACE_UNDER_TEST,
                                                                          create_intf_on_parent_port=True, vrf_name=self.VRF_UNDER_TEST)
        self._test_sub_port_intf_oper_down_with_pending_neigh_route_tasks(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST, vrf_name=self.VRF_UNDER_TEST)
        self._test_sub_port_intf_oper_down_with_pending_neigh_route_tasks(dvs, self.LAG_SUB_PORT_INTERFACE_UNDER_TEST,
                                                                          create_intf_on_parent_port=True, vrf_name=self.VRF_UNDER_TEST)


# Add Dummy always-pass test at end as workaroud
# for issue when Flaky fail on final test it invokes module tear-down before retrying
def test_nonflaky_dummy():
    pass
