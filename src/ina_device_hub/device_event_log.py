import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from ina_device_hub.general_log import logger
from ina_device_hub.setting import setting

MAX_TEXT_PAYLOAD_LENGTH = 4096


def append_device_event(
    event_type: str,
    direction: str,
    device_id: str | None,
    *,
    topic: str | None = None,
    category: str | None = None,
    action: str | None = None,
    kind: str | None = None,
    seq_id: str | int | None = None,
    payload: Any = None,
    occurred_at: str | None = None,
    mqtt_rc: int | None = None,
    retain: bool | None = None,
):
    occurred_at = occurred_at or _utc_now()
    normalized_payload = _normalize_payload(payload)
    event = {
        "occurred_at": occurred_at,
        "event_type": event_type,
        "direction": direction,
        "device_id": device_id,
        "topic": topic,
        "category": category,
        "action": action,
        "kind": kind,
        "seq_id": seq_id,
        "mqtt_rc": mqtt_rc,
        "retain": retain,
        "payload": normalized_payload,
    }
    if isinstance(normalized_payload, dict):
        event.update(_status_derived_fields(occurred_at, normalized_payload))

    try:
        with open(_event_log_path(), "a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n")
    except Exception:
        logger.exception("Failed to append device event log")

    return event


def _event_log_path():
    log_dir = os.path.join(setting().get_work_dir(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, "device_events.jsonl")


def _utc_now():
    return datetime.now(UTC).isoformat()


def _normalize_payload(payload):
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", errors="replace")

    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            if len(payload) <= MAX_TEXT_PAYLOAD_LENGTH:
                return payload
            return {
                "text": payload[:MAX_TEXT_PAYLOAD_LENGTH],
                "truncated": True,
                "original_length": len(payload),
            }

    return payload


def _status_derived_fields(occurred_at: str, payload: dict):
    next_sleep_sec = payload.get("next_sleep_sec")
    if not isinstance(next_sleep_sec, int | float):
        return {}

    occurred_at_dt = datetime.fromisoformat(occurred_at)
    if occurred_at_dt.tzinfo is None:
        occurred_at_dt = occurred_at_dt.replace(tzinfo=UTC)

    return {
        "next_sleep_sec": next_sleep_sec,
        "next_wake_at": (occurred_at_dt + timedelta(seconds=next_sleep_sec)).isoformat(),
    }
