import json
import os

from ina_device_hub.setting import setting
from ina_device_hub.general_log import logger

class LocationRepository:
    location_repo_path = os.path.join(setting().get_work_dir(), ".location_list.json")

    def __init__(self):
        self.location_dict = {}
        self.load()

    def load(self):
        if not os.path.exists(self.location_repo_path):
            # create empty file
            with open(self.location_repo_path, "w") as f:
                f.write("{}")
        try:
            with open(self.location_repo_path, "r") as f:
                self.location_dict = json.load(f)
        except FileNotFoundError:
            pass

    def save(self):
        with open(self.location_repo_path, "w") as f:
            json.dump(self.location_dict, f)

    def get(self, key):
        if key is None:
            return {
                "id": None,
                "name": "",
                "description": "",
                "latitude": 0.0,
                "longitude": 0.0,
                "created_at": "",
                "updated_at": "",
            }
        return self.location_dict.get(key)

    def add(self, sensor_id, info: dict):
        if sensor_id not in self.location_dict:
            self.location_dict[sensor_id] = info
            self.save()

    def remove(self, sensor_id):
        if sensor_id in self.location_dict:
            del self.location_dict[sensor_id]
            self.save()

    def get_all(self):
        return self.location_dict

    def clear(self):
        self.location_dict = {}
        self.save()


# singleton instance
__instance = None


def location_repository():
    global __instance
    if not __instance:
        __instance = LocationRepository()

    return __instance
