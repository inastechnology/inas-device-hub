import json
import os

from ina_device_hub.ina_db_connector import ina_db_connector
from ina_device_hub.setting import setting
from ina_device_hub.general_log import logger


class LocationRepository:
    """
    Location Repository
    @note: The location information is stored in cloud storage and the local file.
        Cloud Storage: Public information only(minimun is location ID)
        Local File: All information(including private information(e.g. longitude, latitude))
    """

    local_location_repo_path = os.path.join(setting().get_work_dir(), ".location_list.json")

    def __init__(self):
        self.location_dict = {}
        self.db_connector = ina_db_connector()
        self.load()

    def load(self):
        locations_db = self.db_connector.fetch_location_all()
        location_dict = {}
        print(locations_db)
        for location in locations_db:
            # location_id TEXT PRIMARY KEY,
            # name TEXT,
            # description TEXT,
            # longitude REAL,
            # latitude REAL,
            # info TEXT,
            # location_type TEXT,
            # country TEXT,
            # city TEXT,
            # created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            # updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            location_dict[location[0]] = {
                "name": location[1],
                "description": location[2],
                "longitude": location[3],
                "latitude": location[4],
                "info": location[5],
                "location_type": location[6],
                "country": location[7],
                "city": location[8],
                "created_at": location[9],
                "updated_at": location[10],
            }

        if not os.path.exists(self.local_location_repo_path):
            # create empty file
            with open(self.local_location_repo_path, "w") as f:
                f.write("{}")
        try:
            with open(self.local_location_repo_path, "r") as f:
                local_location_dict = json.load(f)
                for key in local_location_dict.keys():
                    if key in location_dict:
                        location_dict[key].update(local_location_dict[key])
                self.location_dict = location_dict
        except FileNotFoundError:
            pass

    def save(self):
        with open(self.local_location_repo_path, "w") as f:
            json.dump(self.location_dict, f)

    def get(self, key):
        return self.location_dict.get(key)

    def add(self, sensor_id, info: dict):
        if sensor_id not in self.location_dict:
            self.location_dict[sensor_id] = info
            self.save()

        # upsert to db
        self.db_connector.upsert_location(sensor_id, self.__get_public_info(info))

    def update(self, sensor_id, info: dict):
        if sensor_id in self.location_dict:
            self.location_dict[sensor_id] = info
            self.save()

        # upsert to db
        self.db_connector.upsert_location(sensor_id, self.__get_public_info(info))

    def remove(self, sensor_id):
        if sensor_id in self.location_dict:
            del self.location_dict[sensor_id]
            self.save()

    def get_all(self):
        return self.location_dict

    def clear(self):
        self.location_dict = {}
        self.save()

    def __get_public_info(self, info: dict):
        return {
            "name": info.get("name"),
            "description": info.get("description"),
            "location_type": info.get("location_type", "unknown"),
        }


# singleton instance
__instance = None


def location_repository():
    global __instance
    if not __instance:
        __instance = LocationRepository()

    return __instance
