import json
from functools import lru_cache

from ina_device_hub.device_config_repository import (
    device_config_repository,
    validate_device_config,
)
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
            "moisture_threshold": 0,
            "schedules": [
                {
                    "hour": 7,
                    "minute": 0,
                    "duration_sec": 1,
                    "channel_mask": 1,
                }
            ],
        }

    def get_record(self, device_id: str):
        return self.repository.get_or_create(device_id, self.default_config())

    def get_config(self, device_id: str):
        return self.get_record(device_id)["config"]

    def get_all_records(self):
        return self.repository.get_all()

    def update_config(self, device_id: str, config: dict):
        return self.repository.upsert(device_id, config)

    def record_config_request(self, device_id: str):
        return self.repository.record_config_request(device_id, self.default_config())

    def record_status(self, device_id: str, status: dict):
        return self.repository.record_status(device_id, status)

    def update_metadata(self, device_id: str, metadata: dict):
        return self.repository.update_metadata(device_id, metadata)

    def set_state(self, device_id: str, state: str, approved_by: str | None = None):
        return self.repository.set_state(device_id, state, approved_by=approved_by)

    def list_statuses(self, device_id: str, limit: int = 100):
        return self.repository.list_statuses(device_id, limit=limit)

    def _config_for_reply(self, device_id: str):
        record = self.repository.record_config_request(device_id, self.default_config())
        if record["state"] == "active" and record.get("config"):
            return validate_device_config(record["config"])
        return self.default_config()

    def publish_config(self, device_id: str, action: str, config: dict | None = None, retain: bool = False):
        if self.mqtt_client is None:
            raise RuntimeError("mqtt client is not attached")

        config = validate_device_config(config or self.get_config(device_id))
        topic = f"/{device_id}/kinds/config/{action}"
        payload = json.dumps(config, ensure_ascii=True, separators=(",", ":"))
        result = self.mqtt_client.publish(topic, payload, qos=0, retain=retain)
        if result.rc != 0:
            logger.error(
                "Failed to publish config for device_id=%s topic=%s rc=%s",
                device_id,
                topic,
                result.rc,
            )
        return {"topic": topic, "payload": config, "mqtt_rc": result.rc}

    def publish_reply(self, device_id: str):
        published = self.publish_config(device_id, "reply", config=self._config_for_reply(device_id), retain=False)
        self.repository.record_config_reply(device_id)
        return published

    def publish_push(self, device_id: str):
        return self.publish_config(device_id, "push", retain=True)

    def handle_mqtt_message(self, mqtt_client, message: dict):
        del mqtt_client
        if message.get("message_type") != "device_config":
            return False

        device_id = message["device_id"]
        category = message.get("category")
        action = message.get("action")
        if category == "config" and action == "request":
            try:
                request_payload = _decode_optional_json_payload(message.get("payload"))
                if request_payload is not None and request_payload.get("request") != "runtime_config":
                    logger.warning("Unexpected config request payload for device_id=%s payload=%s", device_id, request_payload)
                self.publish_reply(device_id)
            except Exception:
                logger.exception("Config reply failed for device_id=%s", device_id)
                raise
            return True

        if category == "agri" and action == "immediate":
            try:
                self.record_status(device_id, _decode_json_payload(message.get("payload")))
            except ValueError:
                logger.exception("Status payload parse failure for device_id=%s", device_id)
                return True
            return True

        return False

    def update_and_optionally_push(self, device_id: str, config: dict, push: bool = False):
        record = self.update_config(device_id, config)
        published: dict | None = None
        if push:
            published = self.publish_push(device_id)
        return {"record": record, "published": published}


def _decode_json_payload(payload):
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("payload must be valid JSON") from exc
    else:
        decoded = payload

    if not isinstance(decoded, dict):
        raise ValueError("payload must be a JSON object")
    return decoded


def _decode_optional_json_payload(payload):
    if payload in (None, b"", ""):
        return None

    try:
        return _decode_json_payload(payload)
    except ValueError:
        logger.warning("Ignoring invalid config request payload: %r", payload)
        return None


@lru_cache(maxsize=1)
def device_config_service():
    return DeviceConfigService()
