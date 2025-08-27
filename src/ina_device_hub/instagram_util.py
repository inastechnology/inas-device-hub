import hashlib
import json
import os
import time
from datetime import datetime, timedelta
from io import BytesIO
from typing import Any, Mapping

import requests
from PIL import Image

from ina_device_hub.general_log import logger
from ina_device_hub.setting import setting
from ina_device_hub.storage_connector import storage_connector
from ina_device_hub.utils import Utils


class InstagramUtil:
    """
    ビジネス／クリエイターアカウント向け Instagram Graph API v22.0 ラッパー。
    ・コンテナ作成 → 変換完了待機 → 公開 のフローを _post_media() に集約
    ・ポーリング設定はクラス変数／コンストラクタ引数で一元管理
    """

    # ---- デフォルトのポーリング設定（秒） ----
    DEFAULT_TIMEOUT_PHOTO = 300
    DEFAULT_INTERVAL_PHOTO = 5
    DEFAULT_TIMEOUT_REEL = 600
    DEFAULT_INTERVAL_REEL = 10

    def __init__(
        self,
    ) -> None:
        self.ig_user_id = setting().get("instagram").get("user_id")
        self.ig_user_id_hash = hashlib.sha256(self.ig_user_id.encode()).hexdigest()
        self.access_token = setting().get("instagram").get("access_token")
        self.api_version = setting().get("instagram").get("api_version", "v22.0")
        # API ベース URL
        self.base_url = f"https://graph.facebook.com/{self.api_version}"

        # tmp storage bucket の base URL
        self.tmp_storage_base_url = setting().get("tmp_bucket").get("base_url")

        # クラス変数をインスタンスにコピーして上書き可
        self.timeout_photo = self.DEFAULT_TIMEOUT_PHOTO
        self.interval_photo = self.DEFAULT_INTERVAL_PHOTO
        self.timeout_reel = self.DEFAULT_TIMEOUT_REEL
        self.interval_reel = self.DEFAULT_INTERVAL_REEL

    # ---------- 公開 API ---------- #
    def post_photo_from_bytes(self, *, image_bytes: bytes, caption: str = "") -> str:
        """JPEG 1 枚を通常フィードに投稿。
        image_bytes を一旦S3にアップロードして署名付きURLを生成し、
        そのURLを使って投稿する。
        """
        image_key = storage_connector().save_to_cloud_as_tmp(f"tmp/instagram/{self.ig_user_id_hash}", image_bytes, content_type="image/jpeg")
        image_url = os.path.join(self.tmp_storage_base_url, image_key)
        if not image_url:
            raise RuntimeError("Failed to upload image to cloud storage")

        return self.post_photo(image_url=image_url, caption=caption)

    def post_reel_from_bytes(
        self,
        *,
        video_bytes: bytes,
        caption: str = "",
        cover_bytes: bytes | None = None,
    ) -> str:
        """Reels (～3 分 MP4/MOV) を投稿。
        video_bytes を一旦S3にアップロードして署名付きURLを生成し、
        そのURLを使って投稿する。
        cover_bytes でサムネイル指定可。"""
        video_key = storage_connector().save_to_cloud_as_tmp(f"tmp/instagram/{self.ig_user_id_hash}", video_bytes, content_type="video/mp4")
        video_url = os.path.join(self.tmp_storage_base_url, video_key)
        if not video_url:
            raise RuntimeError("Failed to upload video to cloud storage")

        cover_url = None
        if cover_bytes:
            cover_key = storage_connector().save_to_cloud_as_tmp(f"tmp/instagram/{self.ig_user_id_hash}", cover_bytes, content_type="image/jpeg")
            cover_url = os.path.join(self.tmp_storage_base_url, cover_key)

        return self.post_reel(
            video_url=video_url,
            caption=caption,
            cover_url=cover_url,
        )

    def post_multiple_content(
        self,
        content_list: list[tuple[str, str]],
        caption: str = "",
    ):
        """複数のコンテンツを投稿する。
        content_list は (image_url, caption) のタプルのリスト。
        画像は通常フィード、動画はリールとして投稿される。"""
        container_ids = []
        for content_bytes, content_type in content_list:
            if content_type == "image":
                image_key = storage_connector().save_to_cloud_as_tmp(f"tmp/instagram/{self.ig_user_id_hash}", content_bytes, content_type="image/jpeg")
                image_url = os.path.join(self.tmp_storage_base_url, image_key)
                if not image_url:
                    raise RuntimeError("Failed to upload image to cloud storage")
                container_id = None
                retry = 0
                while not container_id:
                    # コンテナを作成して投稿
                    # 画像は通常フィードに投稿される
                    try:
                        container_id = self._create_container(
                            {
                                "image_url": image_url,
                            }
                        )
                    except Exception as e:
                        logger.error(f"Error creating container for image: {e}")

                    if not container_id:
                        retry += 1
                        if retry > 3:
                            raise RuntimeError("Failed to create container for image")
                        logger.warning(f"Retrying to create container for image ({retry}/3)")
                        time.sleep(retry * 2 + 1)

                logger.info(f"Posted image with ID: {container_id}")
                # コンテナIDをリストに追加
                container_ids.append(container_id)
            elif content_type == "video":
                video_key = storage_connector().save_to_cloud_as_tmp(f"tmp/instagram/{self.ig_user_id_hash}", content_bytes, content_type="video/mp4")
                video_url = os.path.join(self.tmp_storage_base_url, video_key)
                if not video_url:
                    raise RuntimeError("Failed to upload video to cloud storage")

                container_id = None
                retry = 0
                while not container_id:
                    # コンテナを作成して投稿
                    # 動画はリールとして投稿される
                    try:
                        container_id = self._create_container(
                            {
                                "media_type": "REELS",
                                "video_url": video_url,
                            }
                        )
                    except Exception as e:
                        logger.error(f"Error creating container for video: {e}")

                    if not container_id:
                        retry += 1
                        if retry > 3:
                            raise RuntimeError("Failed to create container for video")
                        logger.warning(f"Retrying to create container for video ({retry}/3)")
                        time.sleep(retry * 2 + 1)

                logger.info(f"Posted video with ID: {container_id}")
                # コンテナIDをリストに追加
                container_ids.append(container_id)

            else:
                raise ValueError(f"Unsupported content type: {content_type}")
        if not container_ids:
            raise RuntimeError("No content posted")

        # 作成したコンテナを待つ
        for container_id in container_ids:
            logger.info(f"Waiting for container {container_id} to finish...")
            self._wait_until_finished(container_id, timeout=self.timeout_reel, interval=self.interval_reel)
            logger.info("\t=> Container is ready")
            # 少し待つ
            time.sleep(1)

        # 全てのコンテナを内包するコンテナを作成
        children = ",".join(container_ids)
        container_id = None
        retry = 0
        while not container_id:
            # コンテナを作成して投稿
            # 画像は通常フィード、動画はリールとして投稿される
            try:
                container_id = self._create_container(
                    {
                        "media_type": "CAROUSEL",
                        "children": children,
                        "caption": caption,
                    }
                )
            except Exception as e:
                logger.error(f"Error creating container for multiple content: {e}")

            if not container_id:
                retry += 1
                if retry > 3:
                    raise RuntimeError("Failed to create container for multiple content")
                logger.warning(f"Retrying to create container for multiple content ({retry}/3)")
                time.sleep(retry * 2 + 1)

        logger.info(f"Posted multiple content with ID: {container_id}")
        # コンテナが完成するまで待機
        self._wait_until_finished(container_id, timeout=self.timeout_reel, interval=self.interval_reel)
        time.sleep(1)  # 少し待つ
        # コンテナを公開
        media_id = self._publish_container(container_id)
        logger.info(f"Published multiple content with media ID: {media_id}")
        return media_id

    def post_photo(self, *, image_url: str, caption: str = "") -> str:
        """JPEG 1 枚を通常フィードに投稿。署名付き URL 可。"""
        payload: dict[str, Any] = {
            "image_url": image_url,
            "caption": caption,
        }
        return self._post_media(
            payload,
            timeout=self.timeout_photo,
            interval=self.interval_photo,
        )

    def post_reel(
        self,
        *,
        video_url: str,
        caption: str = "",
        cover_url: str | None = None,
    ) -> str:
        """Reels (～3 分 MP4/MOV) を投稿。cover_url でサムネ指定可。"""
        payload: dict[str, Any] = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
        }
        if cover_url:
            payload["cover_url"] = cover_url

        return self._post_media(
            payload,
            timeout=self.timeout_reel,
            interval=self.interval_reel,
        )

    @staticmethod
    def get_post_url(media_id: str) -> str:
        """投稿されたメディアの URL を取得する。"""
        return f"https://www.instagram.com/p/{media_id}/"

    # ---------- 共通フロー ---------- #

    def _post_media(
        self,
        create_params: Mapping[str, Any],
        *,
        timeout: int,
        interval: int,
    ) -> str:
        """
        1. コンテナ作成
        2. status_code = FINISHED までポーリング
        3. 公開
        成功すれば公開済みメディア ID を返す。
        """
        retry = 0
        retry_limit = 3
        while retry < retry_limit:
            try:
                creation_id = self._create_container(create_params)
                logger.info(f"Waiting for media container {creation_id} to finish...")
                self._wait_until_finished(creation_id, timeout, interval)
                time.sleep(1)
                return self._publish_container(creation_id)
            except Exception as e:
                logger.error(f"Error posting media: {e}")
                retry += 1
                if retry >= retry_limit:
                    raise RuntimeError("Failed to post media after multiple attempts")
                logger.warning(f"Retrying to post media ({retry}/{retry_limit})")
                time.sleep(retry * 2 + 1)  # Exponential backoff

        raise RuntimeError("Failed to post media after retries")

    def _create_container(self, params: Mapping[str, Any]) -> str:
        logger.info(f"Creating media container with params: {json.dumps(params, indent=2, ensure_ascii=False)}")
        # コンテナ作成リクエスト
        res = requests.post(
            f"{self.base_url}/{self.ig_user_id}/media",
            {**params, "access_token": self.access_token, "graph_domain": "https://graph.facebook.com/", "version": self.api_version},
        )
        print(f"Response: {res.text}")
        res.raise_for_status()
        return res.json()["id"]

    def _wait_until_finished(self, creation_id: str, timeout: int, interval: int) -> None:
        endpoint = f"{self.base_url}/{creation_id}?fields=status_code"
        start = time.time()
        auth_headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        logger.info(f"Polling {endpoint} every {interval} seconds until finished or timeout ({timeout} seconds)")
        cnt = 0
        while True:
            res = requests.get(
                endpoint,
                headers=auth_headers,
                timeout=30,
            )
            res.raise_for_status()
            status = res.json().get("status_code")
            if status == "FINISHED":
                logger.info(f"=> Media container {creation_id} is ready")
                return
            if status == "ERROR":
                raise RuntimeError(f"Media container {creation_id} failed")
            if time.time() - start > timeout:
                raise TimeoutError("Polling timed out")
            time.sleep(interval)
            cnt += 1
            logger.info(f"Polling {cnt} times: status_code={status} (elapsed: {time.time() - start:.2f} seconds)")

    def _publish_container(self, creation_id: str) -> str:
        auth_headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        res = requests.post(
            f"{self.base_url}/{self.ig_user_id}/media_publish",
            headers=auth_headers,
            data={"creation_id": creation_id},
            timeout=30,
        )
        res.raise_for_status()
        return res.json()["id"]


__instance = None


def instagram_util():
    global __instance
    if not __instance:
        __instance = InstagramUtil()
    return __instance
