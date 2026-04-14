import json
from functools import lru_cache

from ina_device_hub.device_config_repository import device_config_repository
from ina_device_hub.general_log import logger
from ina_device_hub.setting import setting


class DeviceConfigService:
    def __init__(self, repository=None):
        self.repository = repository or device_config_repository()
        self.mqtt_client = None

    def attach_mqtt_client(self, mqtt_client):
        self.mqtt_client = mqtt_client

    def default_config(self):
        device_config_defaults = setting().get("device_config_defaults")
        return {
            "ntp_server": device_config_defaults["ntp_server"],
            "timezone_offset_sec": device_config_defaults["timezone_offset_sec"],
            "moisture_threshold": device_config_defaults["moisture_threshold"],
            "schedules": [],
        }

    def get_record(self, device_id: str):
        return self.repository.get_or_create(device_id, self.default_config())

    def get_config(self, device_id: str):
        return self.get_record(device_id)["config"]

    def get_all_records(self):
        return self.repository.get_all()

    def update_config(self, device_id: str, config: dict):
        return self.repository.upsert(device_id, config)

    def publish_config(self, device_id: str, action: str):
        if self.mqtt_client is None:
            raise RuntimeError("mqtt client is not attached")

        config = self.get_config(device_id)
        topic = f"/{device_id}/kinds/config/{action}"
        payload = json.dumps(config, ensure_ascii=True)
        result = self.mqtt_client.publish(topic, payload, qos=1, retain=True)
        if result.rc != 0:
            logger.error(
                "Failed to publish config for device_id=%s topic=%s rc=%s",
                device_id,
                topic,
                result.rc,
            )
        return {"topic": topic, "payload": config, "mqtt_rc": result.rc}

    def publish_reply(self, device_id: str):
        return self.publish_config(device_id, "reply")

    def publish_push(self, device_id: str):
        return self.publish_config(device_id, "push")

    def handle_mqtt_message(self, mqtt_client, message: dict):
        del mqtt_client
        if message.get("message_type") != "device_config":
            return False
        if message.get("category") != "config" or message.get("action") != "request":
            return False

        device_id = message["device_id"]
        try:
            self.publish_reply(device_id)
        except Exception:
            logger.exception("Config reply failed for device_id=%s", device_id)
            raise
        return True

    def update_and_optionally_push(self, device_id: str, config: dict, push: bool = False):
        record = self.update_config(device_id, config)
        published: dict | None = None
        if push:
            published = self.publish_push(device_id)
        return {"record": record, "published": published}


@lru_cache(maxsize=1)
def device_config_service():
    return DeviceConfigService()
