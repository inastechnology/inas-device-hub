import json
import os

from ina_device_hub.general_log import logger
from ina_device_hub.ina_db_connector import ina_db_connector

class SensorDeviceRepository:

    def __init__(self):
        self.tmp_sensor_data_dict = {}
        self.db_connector = ina_db_connector()

    def get_by_id(self, sensor_id):
        return self.db_connector.fetch_sensor(sensor_id)
    
    def get_all(self):
        return self.db_connector.fetch_sensors_all()
    
    def get_by_location(self, location_id):
        db_ret_as_tuplelist = self.db_connector.fetch_sensors_by_location_id(location_id)
        ret = []
        for db_ret_as_tuple in db_ret_as_tuplelist:
            ret.append({
                "id": db_ret_as_tuple[0],
                "name": db_ret_as_tuple[1],
                "description": db_ret_as_tuple[2],
                "location_id": db_ret_as_tuple[3],
                "created_at": db_ret_as_tuple[4],
                "updated_at": db_ret_as_tuple[5],
            })
            
        return ret
    
    def add(self, sensor_id, info):
        if self.__is_exist(sensor_id):
            return
        
        self.db_connector.upsert_sensor(sensor_id, info)
        self.tmp_sensor_data_dict[sensor_id] = info
            
        
    def __is_exist(self, sensor_id):
        if sensor_id in self.tmp_sensor_data_dict:
            return True
        
        # check db
        try:
            ret_db  = self.db_connector.fetch_sensor(sensor_id)
            if ret_db:
                # add to tmp
                # -------------------
                # sensor_id TEXT PRIMARY KEY,
                # info TEXT,
                # sensor_type TEXT,
                # firmware_version TEXT,
                # installation_date TIMESTAMP,
                # location_id TEXT,
                # created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                # updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                # FOREIGN KEY (location_id) REFERENCES location_table(location_id)

                self.tmp_sensor_data_dict[sensor_id] = {
                    "id": ret_db[0],
                    "info": ret_db[1],
                    "sensor_type": ret_db[2],
                    "firmware_version": ret_db[3],
                    "installation_date": ret_db[4],
                    "location_id": ret_db[5],
                    "created_at": ret_db[6],
                    "updated_at": ret_db[7],
                }
                return True
            
            return False
        except Exception as e:
            logger.error(f"Failed to fetch sensor data: {e}")
            return False
                    
            
            

# singleton instance
__instance = None


def sensor_device_repository():
    global __instance
    if not __instance:
        __instance = SensorDeviceRepository()

    return __instance
