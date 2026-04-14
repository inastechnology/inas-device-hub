import json
import mimetypes
import os
from datetime import datetime, timedelta
import threading

from apscheduler.schedulers.background import BlockingScheduler

from ina_device_hub.ai_content_service import ai_content_service
from ina_device_hub.camera_device_repository import camera_device_repository
from ina_device_hub.general_log import logger
from ina_device_hub.ina_db_connector import InaDBConnector
from ina_device_hub.instagram_client import InstagramClient
from ina_device_hub.sensor_data_repository import sensor_data_repository
from ina_device_hub.setting import setting
from ina_device_hub.storage_connector import storage_connector
from ina_device_hub.timelapse_media_service import timelapse_media_service


class InstagramPostTask:
    def __init__(self):
        self.settings = setting()
        self.ai_settings = self.settings.get("ai")
        self.instagram_settings = self.settings.get("instagram")
        self.storage_connector = storage_connector()
        self.timelapse_media_service = timelapse_media_service()
        self.sensor_data_repository = sensor_data_repository(InaDBConnector())
        self.camera_repository = camera_device_repository()
        self.ai_content_service = ai_content_service()
        self.scheduler = BlockingScheduler()
        self.state_file_path = os.path.join(
            self.settings.get_work_dir(),
            "instagram_post_task_state.json",
        )

    def start(self):
        if not self.is_enabled() or self.scheduler.running:
            return

        hour, minute = self._parse_schedule()
        self.scheduler.add_job(
            self._run,
            "cron",
            hour=hour,
            minute=minute,
            max_instances=1,
        )
        logger.info(
            f"Start {self.__class__.__name__}"
            f"(schedule: {hour:02d}:{minute:02d})"
        )
        worker_thread = threading.Thread(target=self.scheduler.start)
        worker_thread.daemon = True
        worker_thread.start()

    def is_enabled(self):
        required_values = [
            self.ai_settings.get("enabled"),
            self.instagram_settings.get("user_id"),
            self.instagram_settings.get("access_token"),
            self.instagram_settings.get("camera_id"),
        ]
        if not all(required_values):
            logger.info("InstagramPostTask is disabled by configuration")
            return False
        if not self.storage_connector.is_temporary_storage_configured():
            logger.warning(
                "Temporary storage is not configured; "
                "skip Instagram posting"
            )
            return False
        return True

    def _run(self):
        camera_id = self.instagram_settings.get("camera_id")
        state = self._load_state()
        end_at = datetime.now()
        last_post_at = self._parse_datetime(state.get("last_post_at"))
        start_at = (
            last_post_at + timedelta(seconds=1)
            if last_post_at
            else (end_at - timedelta(days=1))
        )

        video_path = self.timelapse_media_service.create_video(
            camera_id,
            start_at=start_at,
            end_at=end_at,
        )
        if not video_path:
            logger.info(
                "Skip Instagram post because no timelapse is available: "
                f"{camera_id}"
            )
            return

        frame_paths = self.timelapse_media_service.list_frames(
            camera_id,
            start_at=start_at,
            end_at=end_at,
        )
        image_paths = self._select_key_frames(frame_paths)
        image_urls = [
            self._upload_public_asset(image_path)
            for image_path in image_paths
        ]
        image_urls = [image_url for image_url in image_urls if image_url]

        video_url = self._upload_public_asset(video_path)
        if not video_url:
            logger.error("Failed to upload timelapse video for Instagram")
            return

        media_context = self._build_media_context(
            camera_id=camera_id,
            start_at=start_at,
            end_at=end_at,
            frame_paths=frame_paths,
            image_urls=image_urls,
            video_url=video_url,
        )
        caption = self.ai_content_service.generate_instagram_caption(
            media_context
        )
        instagram_client = InstagramClient(
            self.instagram_settings.get("user_id"),
            self.instagram_settings.get("access_token"),
        )
        media_id = instagram_client.publish_reel(
            video_url=video_url,
            caption=caption,
            cover_url=image_urls[-1] if image_urls else None,
        )

        self._save_state(
            {
                "last_post_at": end_at.isoformat(),
                "last_media_id": media_id,
                "last_video_url": video_url,
                "last_caption": caption,
            }
        )
        logger.info(f"Instagram reel published: {media_id}")

    def _build_media_context(
        self,
        camera_id: str,
        start_at: datetime,
        end_at: datetime,
        frame_paths: list[str],
        image_urls: list[str],
        video_url: str,
    ):
        sensor_id = self.instagram_settings.get("sensor_id")
        sensor_snapshot = {}
        if sensor_id:
            latest_sensor = self.sensor_data_repository.get_latest(sensor_id)
            sensor_snapshot = latest_sensor or {}

        camera_info = self.camera_repository.get(camera_id) or {}
        return {
            "camera_id": camera_id,
            "camera_name": camera_info.get("name", camera_id),
            "frame_count": len(frame_paths),
            "start_at": start_at.isoformat(timespec="seconds"),
            "end_at": end_at.isoformat(timespec="seconds"),
            "image_urls": image_urls,
            "video_url": video_url,
            "sensor_snapshot": sensor_snapshot,
            "plant_position_prompt": self.instagram_settings.get(
                "plant_position_prompt"
            ),
        }

    def _select_key_frames(self, frame_paths: list[str]):
        if len(frame_paths) <= 3:
            return frame_paths
        midpoint = len(frame_paths) // 2
        return [
            frame_paths[0],
            frame_paths[midpoint],
            frame_paths[-1],
        ]

    def _upload_public_asset(self, local_path: str):
        relative_key = os.path.join(
            "instagram_publish",
            datetime.now().strftime("%Y%m%d"),
            os.path.basename(local_path),
        )
        with open(local_path, "rb") as file:
            file_bytes = file.read()
        content_type = (
            mimetypes.guess_type(local_path)[0]
            or "application/octet-stream"
        )
        uploaded_key = self.storage_connector.save_bytes_to_temporary_cloud(
            relative_key,
            file_bytes,
            content_type=content_type,
        )
        if not uploaded_key:
            return None
        return self.storage_connector.get_temporary_public_url(uploaded_key)

    def _parse_schedule(self):
        schedule = self.ai_settings.get("agent_schedule_start", "09:01")
        hour_str, minute_str = schedule.split(":", maxsplit=1)
        return int(hour_str), int(minute_str)

    def _load_state(self):
        if not os.path.exists(self.state_file_path):
            return {}
        with open(self.state_file_path, encoding="utf-8") as file:
            return json.load(file)

    def _save_state(self, state: dict):
        with open(self.state_file_path, "w", encoding="utf-8") as file:
            json.dump(state, file, ensure_ascii=False, indent=2)

    def _parse_datetime(self, value: str | None):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None


__instance = None


def instagram_post_task():
    global __instance
    if not __instance:
        __instance = InstagramPostTask()
    return __instance
