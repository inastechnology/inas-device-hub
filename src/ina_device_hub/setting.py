import json
import os
import uuid

from ina_device_hub import ina_env


def get_device_id():
    prefix = "inahub-"
    try:
        # grep Serial /proc/cpuinfo|awk '{print $3}'
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if line.startswith("Serial"):
                    return prefix + line.split(":")[1].strip()
    except FileNotFoundError:
        pass
    return prefix + str(uuid.getnode())


# Default settings
DEFAULT_SETTINGS = {
    "language": os.environ.get("LANGUAGE", "en"),
    "tenant_id": "00000000-0000-0000-0000-000000000000",
    "device_id": get_device_id(),
    "device_name": ina_env.DEVICE_NAME,
    "turso": {
        "database_url": ina_env.TURSO_DATABASE_URL,
        "auth_token": ina_env.TURSO_AUTH_TOKEN,
        "sync_interval": ina_env.TURSO_SYNC_INTERVAL,
        "local_db_path": os.path.join(os.path.expanduser(ina_env.WORK_DIR), "ina.db"),
    },
    "storage_bucket": {
        "endpoint_url": ina_env.S3_ENDPOINT_URL,
        "bucket_name": ina_env.S3_BUCKET_NAME,
        "region": ina_env.S3_BUCKET_REGION,
        "access_key": ina_env.S3_ACCESS_KEY,
        "secret_key": ina_env.S3_SECRET_KEY,
    },
    "local_storage_base_dir": ina_env.LOCAL_STORAGE_BASE_DIR,
    "timelapse_interval": ina_env.TIMELAPSE_INTERVAL,
    "mqtt": {
        "mqtt_broker": ina_env.MQTT_BROKER_URL,
        "mqtt_port": ina_env.MQTT_BROKER_PORT,
        "mqtt_client_id": ina_env.DEVICE_NAME,
        "mqtt_username": ina_env.MQTT_BROKER_USERNAME,
        "mqtt_password": ina_env.MQTT_BROKER_PASSWORD,
    },
    "sensor": {
        "save_image": ina_env.SENSOR_SAVE_IMAGE,
        "save_audio": ina_env.SENSOR_SAVE_AUDIO,
        "blacklist": [],
    },
    "ai": {
        "enabled": False,
        "schedule": {
            "start": ina_env.AI_AGENT_SCHEDULE_START,
        },
        "image_analyze": {
            "api_key": ina_env.AI_IMAGE_ANALYZE_API_KEY,
            "base_url": ina_env.AI_IMAGE_ANALYZE_BASE_URL,
            "model": ina_env.AI_IMAGE_ANALYZE_MODEL,
        },
        "text_analyze": {
            "api_key": ina_env.AI_TEXT_ANALYZE_API_KEY,
            "base_url": ina_env.AI_TEXT_ANALYZE_BASE_URL,
            "model": ina_env.AI_TEXT_ANALYZE_MODEL,
        },
    },
}


""" Setting module
This module provides the settings for the device.

"""


class Setting:
    SETTING_FILE_PATH = os.path.expanduser("~/.ina-device-hub/config.json")

    def __init__(self, path=None):
        if path:
            self.SETTING_FILE_PATH = path
        self.settings = DEFAULT_SETTINGS
        self.load()

    def load(self):
        try:
            with open(self.SETTING_FILE_PATH, "r") as f:
                self.settings = json.load(f)
        except FileNotFoundError:
            pass

    def save(self):
        with open(self.SETTING_FILE_PATH, "w") as f:
            json.dump(self.settings, f, indent=4)

    def get(self, key):
        return self.settings.get(key)

    def set(self, key, value):
        self.settings[key] = value
        self.save()

    def get_work_dir(self):
        return ina_env.WORK_DIR


__instance = None


def setting():
    global __instance
    if not __instance:
        __instance = Setting()

    return __instance
