import hashlib
from datetime import datetime
import os
from src.ina_device_hub.storage_connector import storage_connector
from src.ina_device_hub.general_log import logger
from src.ina_device_hub.setting import setting


class PostImageRepository:
    def __init__(self, storage_connector):
        self.storage_connector = storage_connector
        self.ig_user_id = setting().get("instagram").get("user_id")
        self.ig_user_id_hash = hashlib.sha256(self.ig_user_id.encode()).hexdigest()

    def save_to_cloud(self, img_bytes, title):
        """
        Save the image bytes to cloud storage.
        Automatically generates the file path based on the current date and time(UTC).
        """
        try:
            yyyyymmdd = datetime.utcnow().strftime("%Y%m%d")
            file_key = f"instagram_draft/{self.ig_user_id_hash}/{yyyyymmdd}/{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{title}.jpg"
            # URL encoding the file key
            file_key = os.path.normpath(file_key)
            self.storage_connector.save_to_cloud_as_tmp(file_key, img_bytes, content_type="image/jpeg")
            logger.info(f"Image saved to cloud: {file_key}")
            return file_key
        except Exception as e:
            logger.error(f"Error saving image to cloud: {e}")
            return None

    def fetch_latest_image(self):
        try:
            latest_image = self.storage_connector.fetch_files_from_cloud_as_tmp(f"instagram_draft/{self.ig_user_id_hash}")
            if not latest_image:
                logger.warning("No latest image found.")
                return None

            return latest_image
        except Exception as e:
            logger.error(f"Error fetching latest image: {e}")
            return None
