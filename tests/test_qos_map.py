import pytest
import json
import sys
import time
from swsscommon import swsscommon

CFG_DOT1P_TO_TC_MAP_TABLE_NAME =  "DOT1P_TO_TC_MAP"
CFG_DOT1P_TO_TC_MAP_KEY = "AZURE"
DOT1P_TO_TC_MAP = {
    "0": "0",
    "1": "6",
    "2": "5",
    "3": "3",
    "4": "4",
    "5": "2",
    "6": "1",
    "7": "7",
}

class TestDot1p(object):
    def connect_dbs(self, dvs):
        self.asic_db = swsscommon.DBConnector(1, dvs.redis_sock, 0)
        self.config_db = swsscommon.DBConnector(4, dvs.redis_sock, 0)

    def create_dot1p_profile(self, dvs):
        tbl = swsscommon.Table(self.config_db, CFG_DOT1P_TO_TC_MAP_TABLE_NAME)
        fvs = swsscommon.FieldValuePairs(DOT1P_TO_TC_MAP.items())
        tbl.set(CFG_DOT1P_TO_TC_MAP_KEY, fvs)
        time.sleep(1)

    def apply_dot1p_profile(self, dvs):
        return

    def test_dot1p_cfg(self, dvs):
        self.connect_dbs(dvs)
        self.create_dot1p_profile(dvs)

        # find the created dot1q profile in ASIC_DB
        found = False
        dot1p_tc_map_raw = None
        tbl = swsscommon.Table(self.asic_db, "ASIC_STATE:SAI_OBJECT_TYPE_QOS_MAP")
        keys = tbl.getKeys()
        for key in keys:
            (status, fvs) = tbl.get(key)
            assert status == True

            for fv in fvs:
                if fv[0] == "SAI_QOS_MAP_ATTR_MAP_TO_VALUE_LIST":
                    dot1p_tc_map_raw = fv[1]
                elif fv[0] == "SAI_QOS_MAP_ATTR_TYPE" and fv[1] == "SAI_QOS_MAP_TYPE_DOT1P_TO_TC":
                    found = True

            if found:
                break

        assert found == True

        dot1p_tc_map = json.loads(dot1p_tc_map_raw);
        for dot1p2tc in dot1p_tc_map['list']:
            dot1p = str(dot1p2tc['key']['dot1p'])
            tc = str(dot1p2tc['value']['tc'])
            assert tc == DOT1P_TO_TC_MAP[dot1p]


