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
        # 各センサーがこなすタスク
        # TODO: デバイスごとに設定ページで変更できるようにする
        # センサーからタスク要求が来た場合は、ここで定義されるタスク、スケジュール
        # を参照して、今から実行すべきタスクをセンサーに通知する
        # 通知はMQTTでHEX String形式で送信する
        #
        # |MAGIC Number[2byte]|次のタスク開始までの時間(秒)[4byte]|[タスクID[1byte]][タスクのパラメータ[3byte]]|...[XOR]
        # デバイス側は、タスク開始前に tick を保存しておき、タスク実行後にタスクの所要時間を「次のタスク開始までの時間」から
        # 引いて、次のタスク開始までの時間をSleepする
        "task": {
            "INADS-110387bd-baaa-441b-ada9-0ab58407fd2c": {
                "tasks": [
                    # センサー値報告
                    {
                        "taskName": "sensorDataReport",
                        # Every 30 minutes
                        "schedule": "*/30 * * * *",
                    },
                    # センサ値から必要な液肥の量を計算してポンプを動かす
                    # 肥料の量をどのように計算するかはセンサー側で行う
                    {
                        "taskName": "fertilizer",
                        "pumpId": 1,
                        # ポンプを動かす時間
                        "durationSec": 60,
                        # Every day at 8:00(UTC)
                        "schedule": "0 8 * * *",
                    },
                    # 水やり
                    {
                        "taskName": "watering",
                        "valveId": 1,
                        # ソレノイドバルブ、またはポンプを動かす時間
                        # NOTE: ソレノイドバルブの開閉のクールダウンは
                        #   センサーデバイス側で行うので、ここでは
                        #   積算で何秒開けるかを指定する
                        "durationSec": 300,
                        # Every day at 21:00(UTC)
                        "schedule": "0 21 * * *",
                    },
                ],
            }
        },
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
    "notification": {
        "discord_webhook_url": ina_env.DISCORD_WEBHOOK_URL,
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
