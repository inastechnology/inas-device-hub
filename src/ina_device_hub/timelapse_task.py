from datetime import datetime
import threading

from apscheduler.schedulers.background import BlockingScheduler

from ina_device_hub.camera_connector import camera_connector
from ina_device_hub.camera_image_repository import camera_image_repository
from ina_device_hub.general_log import logger
from ina_device_hub.image_utils import ImageUtils
from ina_device_hub.notification import Notification
from ina_device_hub.sensor_data_repository import sensor_data_repository
from ina_device_hub.setting import setting


class TimelapseTask:
    def __init__(self):
        self.camera_image_repository = camera_image_repository()
        self.sensor_data_repository = sensor_data_repository()
        self.TIMELAPSE_INTERVAL = setting().get("timelapse_interval")

        self.routin_scheduler = BlockingScheduler()

    def start(self):
        if self.routin_scheduler.running:
            return
        self.routin_scheduler.add_job(self.__routin, "interval", seconds=self.TIMELAPSE_INTERVAL, max_instances=1)
        logger.info(f"Start {self.__class__.__name__}(interval: {self.TIMELAPSE_INTERVAL})")
        self.worker_thread = threading.Thread(target=self.routin_scheduler.start)
        self.worker_thread.daemon = True
        self.worker_thread.start()

    def stop(self):
        if self.routin_scheduler.running:
            self.routin_scheduler.shutdown()

        self.worker_thread.join()

    def __routin(self):
        camera = camera_connector()
        camera_list = camera.camera_device_repository.get_all()
        for sensor_id, info in camera_list.items():
            if not info.get("timelapse"):
                # skip devices that are not timelapse
                continue

            img_bytes = camera.take_picture(sensor_id)
            if img_bytes:
                is_on, confidence = ImageUtils.is_led_on_with_confidence(img_bytes)
                print(f"Light status: {is_on}, confidence: {confidence}")
                # TODO: location_id should be fetched from the camera info
                self.sensor_data_repository.update_light_status(None, is_on, confidence)
                self.camera_image_repository.save_to_cloud(sensor_id, img_bytes)
            else:
                logger.error(f"Failed to take picture: {sensor_id}")


__instance = None


def timelapse_task():
    global __instance
    if not __instance:
        __instance = TimelapseTask()

    return __instance
