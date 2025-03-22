from datetime import datetime
import os

from ina_device_hub.storage_connector import storage_connector
from ina_device_hub.camera_device_repository import camera_device_repository
from ina_device_hub.general_log import logger


class CameraImageRepository:
    def __init__(self):
        self.storage_connector = storage_connector()
        self.camera_device_repository = camera_device_repository()

    def save_to_cloud(self, camera_id, img_bytes):
        img_key = self.get_img_key(camera_id)
        self.storage_connector.save_to_cloud(img_key, img_bytes)

    def get_by_id(self, camera_id, limit=10):
        img_key = self.get_img_key(camera_id)
        images = self.storage_connector.fetch_files(img_key, limit)
        return images

    def get_date_image_by_id(self, camera_id: str, date_filter: str, limit=10):
        img_key = self.get_img_key_with_date(camera_id, date_filter)
        print(img_key)
        images = self.storage_connector.fetch_files(img_key, limit)
        return images

    def get_date_image_by_location(self, date_filter: str, location_id: str = None, limit=10):
        ret = {}
        camera_list = self.camera_device_repository.get_by_location(location_id)
        for camera in camera_list:
            img_key = self.get_img_key_with_date(camera["id"], date_filter)
            images = self.storage_connector.fetch_files(img_key, limit)
            if images:
                ret[camera["id"]] = images
        return ret

    def download_image(self, key):
        try:
            response = self.storage_connector.fetch_from_cloud_as_bytes(key)
            return response
        except Exception as e:
            logger.error(f"Error: {e}")
            return None

    @staticmethod
    def get_img_key(camera_id):
        return os.path.join(camera_id, "timelapse")

    @staticmethod
    def get_img_key_with_date(camera_id: str, date: str):
        return os.path.join(CameraImageRepository.get_img_key(camera_id), date)


__instance = None


def camera_image_repository():
    global __instance
    if not __instance:
        __instance = CameraImageRepository()

    return __instance
