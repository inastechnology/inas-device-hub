import os
import tempfile
import unittest

os.environ.setdefault("WORK_DIR", tempfile.mkdtemp())
os.environ.setdefault("TURSO_DATABASE_URL", "x")
os.environ.setdefault("TURSO_AUTH_TOKEN", "x")
os.environ.setdefault("S3_ENDPOINT_URL", "x")
os.environ.setdefault("S3_BUCKET_NAME", "x")
os.environ.setdefault("S3_BUCKET_REGION", "auto")
os.environ.setdefault("S3_ACCESS_KEY", "x")
os.environ.setdefault("S3_SECRET_KEY", "x")
os.environ.setdefault("MQTT_BROKER_URL", "localhost")
os.environ.setdefault("MQTT_BROKER_PORT", "1883")
os.environ.setdefault("MQTT_BROKER_USERNAME", "")
os.environ.setdefault("MQTT_BROKER_PASSWORD", "")
os.environ.setdefault("TIMELAPSE_INTERVAL", "600")

from ina_device_hub.discord_notification_service import DISCORD_CONTENT_LIMIT, format_mqtt_activity  # noqa: E402


class DiscordNotificationServiceTest(unittest.TestCase):
    def test_format_mqtt_activity_includes_topic_device_and_payload(self):
        content = format_mqtt_activity(
            "received",
            "/INADS-00000000-0000-4000-8000-000000000001/kinds/config/request",
            payload=b'{"request":"runtime_config"}',
            parsed_message={
                "message_type": "device_config",
                "device_id": "INADS-00000000-0000-4000-8000-000000000001",
                "category": "config",
                "action": "request",
            },
        )

        self.assertIn("MQTT received", content)
        self.assertIn("topic: /INADS-00000000-0000-4000-8000-000000000001/kinds/config/request", content)
        self.assertIn("device_id: INADS-00000000-0000-4000-8000-000000000001", content)
        self.assertIn('{"request":"runtime_config"}', content)

    def test_format_mqtt_activity_caps_discord_message_length(self):
        content = format_mqtt_activity("received", "farm/device/telemetry", payload={"value": "x" * 5000})

        self.assertLessEqual(len(content), DISCORD_CONTENT_LIMIT)
        self.assertIn("truncated", content)


if __name__ == "__main__":
    unittest.main()
