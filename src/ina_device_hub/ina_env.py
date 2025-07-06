import os
import sys

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
    TURSO_SYNC_INTERVAL = int(os.environ["TURSO_SYNC_INTERVAL"])
except KeyError as e:
    exit(f"Please set {e} in .env file")

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
    exit(f"Please set {e} in .env file")

# MQTT settings
try:
    MQTT_BROKER_URL = os.environ["MQTT_BROKER_URL"]
    MQTT_BROKER_PORT = int(os.environ["MQTT_BROKER_PORT"])
    MQTT_BROKER_USERNAME = os.environ["MQTT_BROKER_USERNAME"]
    MQTT_BROKER_PASSWORD = os.environ["MQTT_BROKER_PASSWORD"]
except KeyError as e:
    exit(f"Please set {e} in .env file")

# sensor settings
try:
    SENSOR_SAVE_IMAGE = bool("true" == os.environ["SENSOR_SAVE_IMAGE"].lower())
    SENSOR_SAVE_AUDIO = bool("true" == os.environ["SENSOR_SAVE_AUDIO"].lower())
except KeyError:
    SENSOR_SAVE_IMAGE = False
    SENSOR_SAVE_AUDIO = False

# AI settings
try:
    AI_ENABLED = bool("true" == os.environ["AI_ENABLED"].lower())
except KeyError:
    AI_ENABLED = False

try:
    AI_AGENT_SCHEDULE_START = os.environ.get("AI_AGENT_SCHEDULE_START", "09:30")
    AI_IMAGE_ANALYZE_API_KEY = os.environ.get("AI_IMAGE_ANALYZE_API_KEY", None)
    AI_IMAGE_ANALYZE_BASE_URL = os.environ.get("AI_IMAGE_ANALYZE_BASE_URL", None)
    AI_IMAGE_ANALYZE_MODEL = os.environ.get("AI_IMAGE_ANALYZE_MODEL", None)

    AI_TEXT_ANALYZE_API_KEY = os.environ.get("AI_TEXT_ANALYZE_API_KEY", None)
    AI_TEXT_ANALYZE_BASE_URL = os.environ.get("AI_TEXT_ANALYZE_BASE_URL", None)
    AI_TEXT_ANALYZE_MODEL = os.environ.get("AI_TEXT_ANALYZE_MODEL", None)

except KeyError:
    if AI_ENABLED:
        sys.exit("Please set AI settings in .env file")
    else:
        AI_AI_AGENT_SCHEDULE_START = None
        AI_IMAGE_ANALYZE_API_KEY = None
        AI_IMAGE_ANALYZE_MODEL = None
        AI_TEXT_ANALYZE_API_KEY = None
        AI_TEXT_ANALYZE_MODEL = None

# Notification settings
try:
    DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]
except KeyError:
    DISCORD_WEBHOOK_URL = None

# other settings
try:
    TIMELAPSE_INTERVAL = int(os.environ["TIMELAPSE_INTERVAL"])
except KeyError:
    exit("Please set TIMELAPSE_INTERVAL in .env file")
