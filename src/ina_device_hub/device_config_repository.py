import copy
import json
import os
from datetime import UTC, datetime
from functools import lru_cache

from ina_device_hub.setting import setting


def _utc_now():
    return datetime.now(UTC).isoformat()


class DeviceConfigValidationError(ValueError):
    pass


class DeviceConfigRepository:
    device_config_path = os.path.join(setting().get_work_dir(), ".device_configs.json")

    def __init__(self):
        self.device_configs = {}
        self.load()

    def load(self):
        if not os.path.exists(self.device_config_path):
            with open(self.device_config_path, "w", encoding="utf-8") as file:
                json.dump({}, file)
        try:
            with open(self.device_config_path, encoding="utf-8") as file:
                self.device_configs = json.load(file)
        except FileNotFoundError:
            self.device_configs = {}

    def save(self):
        with open(self.device_config_path, "w", encoding="utf-8") as file:
            json.dump(self.device_configs, file, ensure_ascii=True, indent=2)

    def get(self, device_id: str):
        record = self.device_configs.get(device_id)
        return copy.deepcopy(record) if record else None

    def get_all(self):
        return copy.deepcopy(self.device_configs)

    def upsert(self, device_id: str, config: dict):
        validated = validate_device_config(config)
        self.device_configs[device_id] = {
            "device_id": device_id,
            "config": validated,
            "updated_at": _utc_now(),
        }
        self.save()
        return copy.deepcopy(self.device_configs[device_id])

    def get_or_create(self, device_id: str, default_config: dict):
        record = self.get(device_id)
        if record is not None:
            return record
        return self.upsert(device_id, default_config)


def validate_device_config(config: dict):
    if not isinstance(config, dict):
        raise DeviceConfigValidationError("config must be an object")

    required_keys = {
        "ntp_server",
        "timezone_offset_sec",
        "moisture_threshold",
        "schedules",
    }
    missing_keys = sorted(required_keys - set(config))
    if missing_keys:
        missing = ", ".join(missing_keys)
        raise DeviceConfigValidationError(f"missing required keys: {missing}")

    ntp_server = config["ntp_server"]
    if not isinstance(ntp_server, str) or not ntp_server.strip():
        raise DeviceConfigValidationError("ntp_server must be a non-empty string")

    timezone_offset_sec = config["timezone_offset_sec"]
    if not isinstance(timezone_offset_sec, int):
        raise DeviceConfigValidationError("timezone_offset_sec must be an integer")

    moisture_threshold = config["moisture_threshold"]
    if not isinstance(moisture_threshold, int) or not 0 <= moisture_threshold <= 100:
        raise DeviceConfigValidationError("moisture_threshold must be between 0 and 100")

    schedules = config["schedules"]
    if not isinstance(schedules, list):
        raise DeviceConfigValidationError("schedules must be an array")

    normalized_schedules = []
    for index, schedule in enumerate(schedules):
        if not isinstance(schedule, dict):
            raise DeviceConfigValidationError(f"schedules[{index}] must be an object")

        required_schedule_keys = {"hour", "minute", "duration_sec", "channel_mask"}
        missing_schedule_keys = sorted(required_schedule_keys - set(schedule))
        if missing_schedule_keys:
            missing = ", ".join(missing_schedule_keys)
            raise DeviceConfigValidationError(
                f"schedules[{index}] missing required keys: {missing}"
            )

        hour = schedule["hour"]
        minute = schedule["minute"]
        duration_sec = schedule["duration_sec"]
        channel_mask = schedule["channel_mask"]

        if not isinstance(hour, int) or not 0 <= hour <= 23:
            raise DeviceConfigValidationError(f"schedules[{index}].hour must be 0-23")
        if not isinstance(minute, int) or not 0 <= minute <= 59:
            raise DeviceConfigValidationError(
                f"schedules[{index}].minute must be 0-59"
            )
        if not isinstance(duration_sec, int) or duration_sec <= 0:
            raise DeviceConfigValidationError(
                f"schedules[{index}].duration_sec must be > 0"
            )
        if not isinstance(channel_mask, int) or channel_mask <= 0:
            raise DeviceConfigValidationError(
                f"schedules[{index}].channel_mask must be > 0"
            )

        normalized_schedules.append(
            {
                "hour": hour,
                "minute": minute,
                "duration_sec": duration_sec,
                "channel_mask": channel_mask,
            }
        )

    return {
        "ntp_server": ntp_server.strip(),
        "timezone_offset_sec": timezone_offset_sec,
        "moisture_threshold": moisture_threshold,
        "schedules": normalized_schedules,
    }


@lru_cache(maxsize=1)
def device_config_repository():
    return DeviceConfigRepository()
