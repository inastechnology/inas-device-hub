import json
import os
import sys
import uuid
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

# device name
try:
    DEVICE_NAME = os.environ["HOSTNAME"]
except KeyError:
    DEVICE_NAME = "ina-device-hub"

# work directory
try:
    WORK_DIR = os.environ["WORK_DIR"]
    WORK_DIR = os.path.expanduser(WORK_DIR)
except KeyError:
    WORK_DIR = os.path.expanduser("~/.ina-device-hub")

if not os.path.exists(WORK_DIR):
    os.makedirs(WORK_DIR)

# Turso settings
try:
    TURSO_DATABASE_URL = os.environ["TURSO_DATABASE_URL"]
    TURSO_AUTH_TOKEN = os.environ["TURSO_AUTH_TOKEN"]
except KeyError as e:
    sys.exit(f"Please set {e} in .env file")

try:
    LOCAL_STORAGE_BASE_DIR = os.environ["LOCAL_STORAGE_BASE_DIR"]
except KeyError:
    LOCAL_STORAGE_BASE_DIR = "./.data/storage"

if not os.path.exists(LOCAL_STORAGE_BASE_DIR):
    os.makedirs(LOCAL_STORAGE_BASE_DIR)

try:
    S3_ENDPOINT_URL = os.environ["S3_ENDPOINT_URL"]
    S3_BUCKET_NAME = os.environ["S3_BUCKET_NAME"]
    S3_BUCKET_REGION = os.environ["S3_BUCKET_REGION"]
    S3_ACCESS_KEY = os.environ["S3_ACCESS_KEY"]
    S3_SECRET_KEY = os.environ["S3_SECRET_KEY"]
except KeyError as e:
    sys.exit(f"Please set {e} in .env file")

# MQTT settings
try:
    MQTT_BROKER_URL = os.environ["MQTT_BROKER_URL"]
    MQTT_BROKER_PORT = int(os.environ["MQTT_BROKER_PORT"])
    MQTT_BROKER_USERNAME = os.environ["MQTT_BROKER_USERNAME"]
    MQTT_BROKER_PASSWORD = os.environ["MQTT_BROKER_PASSWORD"]
except KeyError as e:
    sys.exit(f"Please set {e} in .env file")

# sensor settings
try:
    SENSOR_SAVE_IMAGE = bool("true" == os.environ["SENSOR_SAVE_IMAGE"].lower())
    SENSOR_SAVE_AUDIO = bool("true" == os.environ["SENSOR_SAVE_AUDIO"].lower())
except KeyError:
    SENSOR_SAVE_IMAGE = False
    SENSOR_SAVE_AUDIO = False

# other settings
try:
    TIMELAPSE_INTERVAL = int(os.environ["TIMELAPSE_INTERVAL"])
except KeyError:
    sys.exit("Please set TIMELAPSE_INTERVAL in .env file")

DEVICE_CONFIG_DEFAULT_NTP_SERVER = os.environ.get(
    "DEVICE_CONFIG_DEFAULT_NTP_SERVER", DEVICE_NAME
)
DEVICE_CONFIG_DEFAULT_TIMEZONE_OFFSET_SEC = int(
    os.environ.get("DEVICE_CONFIG_DEFAULT_TIMEZONE_OFFSET_SEC", "32400")
)
DEVICE_CONFIG_DEFAULT_MOISTURE_THRESHOLD = int(
    os.environ.get("DEVICE_CONFIG_DEFAULT_MOISTURE_THRESHOLD", "35")
)


def get_device_id():
    prefix = "inahub-"
    try:
        # grep Serial /proc/cpuinfo|awk '{print $3}'
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("Serial"):
                    return prefix + line.split(":")[1].strip()
    except FileNotFoundError:
        pass
    return prefix + str(uuid.getnode())


# Default settings
DEFAULT_SETTINGS = {
    "tenant_id": "00000000-0000-0000-0000-000000000000",
    "device_id": get_device_id(),
    "device_name": DEVICE_NAME,
    "turso": {
        "database_url": TURSO_DATABASE_URL,
        "auth_token": TURSO_AUTH_TOKEN,
        "local_db_path": os.path.join(os.path.expanduser(WORK_DIR), "ina.db"),
    },
    "storage_bucket": {
        "endpoint_url": S3_ENDPOINT_URL,
        "bucket_name": S3_BUCKET_NAME,
        "region": S3_BUCKET_REGION,
        "access_key": S3_ACCESS_KEY,
        "secret_key": S3_SECRET_KEY,
    },
    "local_storage_base_dir": LOCAL_STORAGE_BASE_DIR,
    "timelapse_interval": TIMELAPSE_INTERVAL,
    "mqtt": {
        "mqtt_broker": MQTT_BROKER_URL,
        "mqtt_port": MQTT_BROKER_PORT,
        "mqtt_client_id": DEVICE_NAME,
        "mqtt_username": MQTT_BROKER_USERNAME,
        "mqtt_password": MQTT_BROKER_PASSWORD,
    },
    "sensor": {
        "save_image": SENSOR_SAVE_IMAGE,
        "save_audio": SENSOR_SAVE_AUDIO,
        "blacklist": [],
    },
    "device_config_defaults": {
        "ntp_server": DEVICE_CONFIG_DEFAULT_NTP_SERVER,
        "timezone_offset_sec": DEVICE_CONFIG_DEFAULT_TIMEZONE_OFFSET_SEC,
        "moisture_threshold": DEVICE_CONFIG_DEFAULT_MOISTURE_THRESHOLD,
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
            with open(self.SETTING_FILE_PATH) as f:
                self.settings = json.load(f)
        except FileNotFoundError:
            pass

    def save(self):
        with open(self.SETTING_FILE_PATH, "w") as f:
            json.dump(self.settings, f)

    def get(self, key):
        return self.settings.get(key)

    def set(self, key, value):
        self.settings[key] = value
        self.save()

    def get_work_dir(self):
        return WORK_DIR


@lru_cache(maxsize=1)
def setting():
    return Setting()
