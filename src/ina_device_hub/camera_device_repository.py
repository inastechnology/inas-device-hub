import json
import os
import uuid

from ina_device_hub.setting import setting
from ina_device_hub.general_log import logger
from ina_device_hub.ina_db_connector import ina_db_connector

class CameraDeviceRepository:
    camera_device_repo_path = os.path.join(
        setting().get_work_dir(), ".camera_device_list.json"
    )

    def __init__(self):
        self.db_connector = ina_db_connector()
        self.camera_dict = {}
        self.load()

    def load(self):
        if not os.path.exists(self.camera_device_repo_path):
            # create empty file
            with open(self.camera_device_repo_path, "w") as f:
                f.write("{}")
        try:
            with open(self.camera_device_repo_path, "r") as f:
                self.camera_dict = json.load(f)
        except FileNotFoundError:
            pass

    def save(self):
        with open(self.camera_device_repo_path, "w") as f:
            json.dump(self.camera_dict, f, indent=4)

    def get(self, key):
        return self.camera_dict.get(key)

    def get_by_location(self, location_id: str = None):
        ret = []
        for camera_id, camera_info in self.camera_dict.items():
            if camera_info.get("location_id") == location_id:
                ret.append(camera_info)
        return ret

    def add(self, camera_id: str = None, info: dict = {}):
        if camera_id is None:
            # generate new camera_id
            camera_id = f"INACD-{str(uuid.uuid4())}"

        if camera_id not in self.camera_dict:
            info["id"] = camera_id
            self.camera_dict[camera_id] = info
            self.db_connector.upsert_camera_device(camera_id, info)
            self.save()

    def remove(self, camera_id):
        if camera_id in self.camera_dict:
            del self.camera_dict[camera_id]
            self.save()

    def get_all(self):
        return self.camera_dict

    def clear(self):
        self.camera_dict = {}
        self.save()


# singleton instance
__instance = None


def camera_device_repository():
    global __instance
    if not __instance:
        __instance = CameraDeviceRepository()

    return __instance
