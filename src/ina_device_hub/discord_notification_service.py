import json
import threading
from datetime import UTC, datetime
from urllib import error, request

from ina_device_hub.general_log import logger
from ina_device_hub.setting import setting

DISCORD_CONTENT_LIMIT = 2000
PAYLOAD_PREVIEW_LIMIT = 900


class DiscordNotificationService:
    def __init__(self, webhook_url: str | None = None):
        discord_settings = setting().get("discord") or {}
        self.webhook_url = (webhook_url if webhook_url is not None else discord_settings.get("webhook_url", "")).strip()

    def enabled(self):
        return bool(self.webhook_url)

    def notify_mqtt_activity(self, direction: str, topic: str, payload=None, parsed_message: dict | None = None, mqtt_rc: int | None = None):
        if not self.enabled():
            return

        content = format_mqtt_activity(direction, topic, payload=payload, parsed_message=parsed_message, mqtt_rc=mqtt_rc)
        worker_thread = threading.Thread(target=self._post, args=(content,), daemon=True)
        worker_thread.start()

    def _post(self, content: str):
        body = json.dumps({"content": content}, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            self.webhook_url,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "ina-device-hub"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=5) as response:
                if response.status >= 300:
                    logger.warning("Discord webhook returned status=%s", response.status)
        except error.HTTPError as exc:
            logger.warning("Discord webhook failed with status=%s", exc.code)
        except Exception:
            logger.exception("Discord webhook notification failed")


def format_mqtt_activity(direction: str, topic: str, payload=None, parsed_message: dict | None = None, mqtt_rc: int | None = None):
    parsed_message = parsed_message or {}
    lines = [
        f"[INA Device Hub] MQTT {direction}",
        f"time: {datetime.now(UTC).isoformat()}",
        f"topic: {topic}",
    ]

    if mqtt_rc is not None:
        lines.append(f"mqtt_rc: {mqtt_rc}")

    for key in ("message_type", "device_id", "kind", "category", "action", "seqId"):
        value = parsed_message.get(key)
        if value is not None:
            lines.append(f"{key}: {value}")

    payload_preview = _payload_preview(payload)
    if payload_preview:
        lines.append("payload:")
        lines.append(f"```json\n{payload_preview}\n```")

    content = "\n".join(lines)
    if len(content) > DISCORD_CONTENT_LIMIT:
        content = content[: DISCORD_CONTENT_LIMIT - 20] + "\n...[truncated]"
    return content


def _payload_preview(payload):
    if payload is None:
        return ""

    if isinstance(payload, bytes):
        text = payload.decode("utf-8", errors="replace")
    elif isinstance(payload, str):
        text = payload
    else:
        try:
            text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        except TypeError:
            text = str(payload)

    text = text.strip()
    if len(text) > PAYLOAD_PREVIEW_LIMIT:
        text = text[:PAYLOAD_PREVIEW_LIMIT] + "...[truncated]"
    return text


def discord_notification_service():
    return DiscordNotificationService()
