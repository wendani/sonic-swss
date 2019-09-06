import pytest
import time
from swsscommon import swsscommon

CFG_VLAN_SUB_INTF_TABLE_NAME = "VLAN_SUB_INTERFACE"
CFG_PORT_TABLE_NAME = "PORT"

STATE_PORT_TABLE_NAME = "PORT_TABLE"

APP_INTF_TABLE_NAME = "INTF_TABLE"

ADMIN_STATUS = "admin_status"


class TestSubPortIntf(object):
    ASIC_RIF_TABLE = "ASIC_STATE:SAI_OBJECT_TYPE_ROUTER_INTERFACE"

    expected_attributes = {
        "SAI_ROUTER_INTERFACE_ATTR_MTU": "9100",
        "SAI_ROUTER_INTERFACE_ATTR_PORT_ID": "oid:0x100000000014a",
        "SAI_ROUTER_INTERFACE_ATTR_SRC_MAC_ADDRESS": "7C:FE:90:F9:3E:80",
        "SAI_ROUTER_INTERFACE_ATTR_TYPE": "SAI_ROUTER_INTERFACE_TYPE_SUB_PORT",
        "SAI_ROUTER_INTERFACE_ATTR_VIRTUAL_ROUTER_ID": "oid:0x3000000000010",
        "SAI_ROUTER_INTERFACE_ATTR_VLAN_ID": "oid:0x2600000000059b"
    }

    PHYSICAL_PORT_UNDER_TEST = "Ethernet64"
    SUB_PORT_INTERFACE_UNDER_TEST = "Ethernet64.10"

    def connect_dbs(self, dvs):
        self.config_db = swsscommon.DBConnector(swsscommon.CONFIG_DB, dvs.redis_sock, 0)
        self.state_db = swsscommon.DBConnector(swsscommon.STATE_DB, dvs.redis_sock, 0)
        self.appl_db = swsscommon.DBConnector(swsscommon.APPL_DB, dvs.redis_sock, 0)

    def set_parent_port_admin_status(self, port_name, status):
        fvs = swsscommon.FieldValuePairs([(ADMIN_STATUS, status)])

        tbl = swsscommon.Table(self.config_db, CFG_PORT_TABLE_NAME)
        tbl.set(port_name, fvs)

        time.sleep(1)

    def create_sub_port_intf_profile(self, sub_port_intf_name):
        fvs = swsscommon.FieldValuePairs([(ADMIN_STATUS, "up")])

        tbl = swsscommon.Table(self.config_db, CFG_VLAN_SUB_INTF_TABLE_NAME)
        tbl.set(sub_port_intf_name, fvs)

        time.sleep(1)

    def check_sub_port_intf_fvs(self, db, table_name, sub_port_intf_name, fv_dict):
        tbl = swsscommon.Table(db, table_name)

        keys = tbl.getKeys()
        assert sub_port_intf_name in keys

        (status, fvs) = tbl.get(sub_port_intf_name)
        assert status == True
        assert len(fvs) == len(fv_dict)

        for field, value in fvs:
            assert fv_dict[field] == value, \
                "Wrong value %s for field %s, expected value: %s" % (value, field, fv_dict[field])

    def check_state_db_sub_port_intf_profile(self, table_name, sub_port_intf_name):
        tbl = swsscommon.Table(self.state_db, table_name)

        keys = tbl.getKeys()
        assert sub_port_intf_name in keys

        (status, fvs) = tbl.get(sub_port_intf_name)
        assert status == True
        assert len(fvs) == 1

        assert fvs[0][0] == "state"
        assert fvs[0][1] == "ok"

    def check_appl_db_sub_port_intf_profile(self, sub_port_intf_name):
        tbl = swsscommon.Table(self.appl_db, APP_INTF_TABLE_NAME)

        keys = tbl.getKeys()
        assert sub_port_intf_name in keys

        (status, fvs) = tbl.get(sub_port_intf_name)
        assert status == True
        assert len(fvs) == 1

        assert fvs[0][0] == ADMIN_STATUS
        assert fvs[0][1] == "up"

    def test_sub_port_intf_creation(self, dvs):
        self.connect_dbs(dvs)

        self.set_parent_port_admin_status(self.PHYSICAL_PORT_UNDER_TEST, "up")
        self.create_sub_port_intf_profile(self.SUB_PORT_INTERFACE_UNDER_TEST)

        # Verify that sub port interface state ok is pushed to STATE_DB by Intfmgrd
        fv_dict = {
            "state" : "ok",
        }
        self.check_sub_port_intf_fvs(self.state_db, STATE_PORT_TABLE_NAME, self.SUB_PORT_INTERFACE_UNDER_TEST, fv_dict)

        fv_dict = {
            ADMIN_STATUS : "down",
        }
        # Verify that sub port interface configuration is synced to APPL_DB INTF_TABLE by Intfmgrd
        self.check_sub_port_intf_fvs(self.appl_db, APP_INTF_TABLE_NAME, self.SUB_PORT_INTERFACE_UNDER_TEST, fv_dict)


    #check_object(asic_db, self.ASIC_RIF_TABLE,
