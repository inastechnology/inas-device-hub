import os
import time
import boto3
import json
from datetime import datetime, timezone, timedelta, UTC

from ina_device_hub.setting import setting
from ina_device_hub.general_log import logger


class StorageConnector:
    """
    StorageConnector is a class that provides a way to save and fetch data from cloud storage.

    Attributes:
    LOCAL_STORAGE_BASE_DIR: str - The base directory for saving files.
    s3: boto3.client - The boto3 client for S3.

    Methods:
    save_to_cloud: str - Saves the file to cloud storage.
    fetch_from_cloud_as_bytes: str - Fetches the file from cloud storage as bytes.

    """

    LOCAL_STORAGE_BASE_DIR = f"{setting().get('local_storage_base_dir')}"

    def __init__(self):
        if not os.path.exists(self.LOCAL_STORAGE_BASE_DIR):
            os.makedirs(self.LOCAL_STORAGE_BASE_DIR)

        self.cache_table_dir = os.path.join(setting().get_work_dir(), ".storage.cache")
        self.cache_table = {}
        if not os.path.exists(self.cache_table_dir):
            os.makedirs(self.cache_table_dir)

        self.s3 = boto3.client(
            "s3",
            endpoint_url=setting().get("storage_bucket").get("endpoint_url"),
            aws_access_key_id=setting().get("storage_bucket").get("access_key"),
            aws_secret_access_key=setting().get("storage_bucket").get("secret_key"),
            region_name=setting().get("storage_bucket").get("region"),
        )

    def save_to_cloud(self, file_key, file_bytes, content_type="image/jpeg"):
        """
        Saves the file to cloud storage.
        Automatically generates the file path based on the file key and the current date and time(UTC).
        e.g.) file path: {tenant_id}/{file_key}/{yyyymmdd}/{yyyymmdd_hhmmss}.jpg
        """
        file_path = self.get_file_path(file_key)
        try:
            # TODO: [Multi-tenancy] The bucket name should be generated based on the tenant_id.
            self.s3.put_object(
                Bucket=setting().get("storage_bucket").get("bucket_name"),
                Key=file_path,
                Body=file_bytes,
                ContentType=content_type,
            )
            logger.info(f"Image uploaded to {file_path}({len(file_bytes)} bytes)")
        except Exception as e:
            logger.exception(f"Error: {e}")
            return None
        return file_path

    def save_to_local(self, file_key, file_bytes):
        file_path = os.path.join(
            self.LOCAL_STORAGE_BASE_DIR,
            self.get_file_path(file_key),
        )
        file_dir = os.path.dirname(file_path)
        if not os.path.exists(file_dir):
            os.makedirs(file_dir)
        with open(file_path, "wb") as f:
            f.write(file_bytes)

        return file_path

    def fetch_from_cloud_as_bytes(self, file_full_key):
        try:
            # TODO: [Multi-tenancy] The bucket name should be generated based on the tenant_id.
            response = self.s3.get_object(
                Bucket=setting().get("storage_bucket").get("bucket_name"),
                Key=file_full_key,
            )
            return response["Body"].read()
        except Exception as e:
            logger.exception(f"Error: {e}")
            return None

    def fetch_files(self, prefix, limit=1, cache=True):
        """
        Fetches the files from cloud storage.
        Automatically generates the prefix based on the file key and the date.
        e.g.) prefix: {tenant_id}/{file_key}/{yyyymmdd}
        """
        print(self.get_prefix(prefix))
        try:
            images = []
            response = self.s3.list_objects_v2(
                Bucket=setting().get("storage_bucket").get("bucket_name"),
                Prefix=self.get_prefix(prefix),
                MaxKeys=limit,
            )
            for content in response.get("Contents", []):
                try:
                    cache_item = self.cache_table.get(content.get("Key"))
                    if cache_item and int(cache_item.get("expire_in", 0)) > int(datetime.now(timezone.utc).timestamp()):
                        logger.info(f"Cache hit: {content.get('Key')}")
                        images.append(
                            {
                                "key": cache_item.get("key"),
                                "last_modified": cache_item.get("last_modified"),
                                "presigned_url": cache_item.get("presigned_url"),
                            }
                        )
                        continue

                    presigned_url = self.get_presigned_url(content.get("Key"))
                    logger.info(presigned_url)
                    images.append(
                        {
                            "key": content.get("Key"),
                            "last_modified": content.get("LastModified"),
                            "presigned_url": presigned_url,
                        }
                    )
                    # register cache table
                    if cache:
                        self.cache_table[content.get("Key")] = {
                            "key": content.get("Key"),
                            "last_modified": content.get("LastModified"),
                            "presigned_url": presigned_url,
                            "expire_in": int(datetime.now(UTC).timestamp() + 24 * 60 * 60),
                        }
                except Exception as e:
                    logger.exception(f"Error: {e}")
            images.sort(key=lambda x: x.get("key"))
            return images
        except Exception as e:
            logger.exception(f"Error: {e}")
            return None

    def get_presigned_url(self, file_full_key):
        try:
            ret = self.s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": setting().get("storage_bucket").get("bucket_name"), "Key": file_full_key},
                ExpiresIn=24 * 60 * 60,
            )
            return ret
        except Exception as e:
            logger.exception(f"Error: {e}")
            return None

    def get_file_dir(self, file_key):
        yyyymmdd = time.strftime("%Y%m%d", time.gmtime())
        return os.path.join(setting().get("tenant_id"), file_key, yyyymmdd)

    def get_file_path(self, file_key):
        return os.path.join(
            self.get_file_dir(file_key),
            time.strftime("%Y%m%d_%H%M%S", time.gmtime()) + ".jpg",
        )

    def get_prefix(self, file_key):
        return os.path.join(setting().get("tenant_id"), file_key)


# singleton instance
__instance = None


def storage_connector():
    global __instance
    if not __instance:
        __instance = StorageConnector()
    return __instance
