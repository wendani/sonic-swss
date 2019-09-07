import pytest
import time
from swsscommon import swsscommon

CFG_VLAN_SUB_INTF_TABLE_NAME = "VLAN_SUB_INTERFACE"
CFG_PORT_TABLE_NAME = "PORT"

STATE_PORT_TABLE_NAME = "PORT_TABLE"

APP_INTF_TABLE_NAME = "INTF_TABLE"

ASIC_RIF_TABLE = "ASIC_STATE:SAI_OBJECT_TYPE_ROUTER_INTERFACE"

ADMIN_STATUS = "admin_status"


class TestSubPortIntf(object):
    PHYSICAL_PORT_UNDER_TEST = "Ethernet64"
    SUB_PORT_INTERFACE_UNDER_TEST = "Ethernet64.10"

    def connect_dbs(self, dvs):
        self.config_db = swsscommon.DBConnector(swsscommon.CONFIG_DB, dvs.redis_sock, 0)
        self.state_db = swsscommon.DBConnector(swsscommon.STATE_DB, dvs.redis_sock, 0)
        self.appl_db = swsscommon.DBConnector(swsscommon.APPL_DB, dvs.redis_sock, 0)
        self.asic_db = swsscommon.DBConnector(swsscommon.ASIC_DB, dvs.redis_sock, 0)

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

    def check_sub_port_intf_fvs(self, db, table_name, key, fv_dict):
        tbl = swsscommon.Table(db, table_name)

        keys = tbl.getKeys()
        assert key in keys

        (status, fvs) = tbl.get(key)
        assert status == True
        assert len(fvs) >= len(fv_dict)

        for field, value in fvs:
            if field in fv_dict:
                assert fv_dict[field] == value, "Wrong value for field %s: %s, expected value: %s" % (field, value, fv_dict[field])

    def get_rif_oids(self):
        tbl = swsscommon.Table(self.asic_db, ASIC_RIF_TABLE)
        return set(tbl.getKeys())

    def get_newly_created_rif_oid(self, old_rifs):
        new_rifs = self.get_rif_oids()
        rif = list(new_rifs - old_rifs)
        assert len(rif) == 1, "Wrong # of newly created rifs, expected #: 1."
        return rif[0]

    def test_sub_port_intf_creation(self, dvs):
        self.connect_dbs(dvs)

        old_rif_oids = self.get_rif_oids()

        self.set_parent_port_admin_status(self.PHYSICAL_PORT_UNDER_TEST, "up")
        self.create_sub_port_intf_profile(self.SUB_PORT_INTERFACE_UNDER_TEST)

        # Verify that sub port interface state ok is pushed to STATE_DB by Intfmgrd
        fv_dict = {
            "state": "ok",
        }
        self.check_sub_port_intf_fvs(self.state_db, STATE_PORT_TABLE_NAME, self.SUB_PORT_INTERFACE_UNDER_TEST, fv_dict)

        # Verify that sub port interface configuration is synced to APPL_DB INTF_TABLE by Intfmgrd
        fv_dict = {
            ADMIN_STATUS: "up",
        }
        self.check_sub_port_intf_fvs(self.appl_db, APP_INTF_TABLE_NAME, self.SUB_PORT_INTERFACE_UNDER_TEST, fv_dict)

        # Verify that a sub port router interface entry is created in ASIC_DB
        fv_dict = {
            "SAI_ROUTER_INTERFACE_ATTR_TYPE": "SAI_ROUTER_INTERFACE_TYPE_SUB_PORT",
            "SAI_ROUTER_INTERFACE_ATTR_OUTER_VLAN_ID": "10",
            "SAI_ROUTER_INTERFACE_ATTR_ADMIN_V4_STATE": "true",
            "SAI_ROUTER_INTERFACE_ATTR_ADMIN_V6_STATE": "true",
            "SAI_ROUTER_INTERFACE_ATTR_MTU": "9100",
        }
        rif_oid = self.get_newly_created_rif_oid(old_rif_oids)
        self.check_sub_port_intf_fvs(self.asic_db, ASIC_RIF_TABLE, rif_oid, fv_dict)
