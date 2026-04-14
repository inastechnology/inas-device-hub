import os
import shutil
import tempfile
from datetime import datetime

import ffmpeg

from ina_device_hub.general_log import logger
from ina_device_hub.setting import setting
from ina_device_hub.storage_connector import storage_connector


class TimelapseMediaService:
    def __init__(self):
        self.local_storage_base_dir = setting().get("local_storage_base_dir")
        self.storage_connector = storage_connector()

    def save_frame(
        self,
        device_id: str,
        image_bytes: bytes,
        captured_at: datetime | None = None,
    ):
        captured_at = captured_at or datetime.now()
        relative_path = self.get_frame_relative_path(device_id, captured_at)
        return self.storage_connector.save_bytes_to_local_path(
            relative_path, image_bytes
        )

    def get_frame_relative_path(self, device_id: str, captured_at: datetime):
        return os.path.join(
            "timelapse_frames",
            device_id,
            captured_at.strftime("%Y%m%d"),
            captured_at.strftime("%Y%m%d_%H%M%S") + ".jpg",
        )

    def list_frames(
        self,
        device_id: str,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ):
        device_dir = os.path.join(
            self.local_storage_base_dir,
            "timelapse_frames",
            device_id,
        )
        if not os.path.exists(device_dir):
            return []

        frames = []
        for root, _, files in os.walk(device_dir):
            for file_name in sorted(files):
                if not file_name.endswith(".jpg"):
                    continue
                file_timestamp = self._parse_frame_timestamp(file_name)
                if file_timestamp is None:
                    continue
                if start_at and file_timestamp < start_at:
                    continue
                if end_at and file_timestamp > end_at:
                    continue
                frames.append(os.path.join(root, file_name))
        return sorted(frames)

    def create_video(
        self,
        device_id: str,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        fps: int = 12,
    ):
        frame_paths = self.list_frames(
            device_id,
            start_at=start_at,
            end_at=end_at,
        )
        if len(frame_paths) < 2:
            return None

        output_relative_path = self.get_video_relative_path(
            device_id, end_at or datetime.now()
        )
        output_path = os.path.join(self.local_storage_base_dir, output_relative_path)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="timelapse-") as staging_dir:
            for index, frame_path in enumerate(frame_paths, start=1):
                staged_path = os.path.join(staging_dir, f"frame_{index:06d}.jpg")
                shutil.copyfile(frame_path, staged_path)

            input_pattern = os.path.join(staging_dir, "frame_%06d.jpg")
            try:
                (
                    ffmpeg.input(input_pattern, framerate=fps, start_number=1)
                    .output(
                        output_path,
                        vcodec="libx264",
                        pix_fmt="yuv420p",
                        movflags="+faststart",
                    )
                    .overwrite_output()
                    .run(capture_stdout=True, capture_stderr=True)
                )
            except ffmpeg.Error as error:
                logger.error(error.stderr.decode())
                return None

        return output_path

    def get_video_relative_path(self, device_id: str, captured_at: datetime):
        return os.path.join(
            "timelapse_videos",
            device_id,
            captured_at.strftime("%Y%m%d"),
            captured_at.strftime("%Y%m%d_%H%M%S") + ".mp4",
        )

    def _parse_frame_timestamp(self, file_name: str):
        stem, _ = os.path.splitext(file_name)
        try:
            return datetime.strptime(stem, "%Y%m%d_%H%M%S")
        except ValueError:
            return None


__instance = None


def timelapse_media_service():
    global __instance
    if not __instance:
        __instance = TimelapseMediaService()
    return __instance
