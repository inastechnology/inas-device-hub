from datetime import datetime, timedelta
from io import BytesIO
import os
from ina_device_hub.instagram_util import instagram_util
from ina_device_hub.general_log import logger
from ina_device_hub.setting import setting
from ina_device_hub.utils import Utils
from PIL import Image


class InstagramPoster:
    def __init__(self):
        self.instagram_util = instagram_util()

    def post_evaluate_image(self, image_bytes, caption):
        # ここにInstagramへの画像投稿ロジックを実装
        self.instagram_util.post_photo_from_bytes(image_bytes=image_bytes, caption=caption)

    def post_growth_record(self, image_bytes_list: list[bytes], caption, mp4_bytes: list[bytes], cover_image_bytes: bytes = None):
        """
        指定した成長画像をInstagramに投稿する。
        :param image_bytes_list: 投稿する画像のバイト列のリスト
        :param caption: 投稿のキャプション
        :param reel_image_bytes_list: リール動画に使用する画像のバイト列のリスト
        """
        media_id = self.instagram_util.post_reel_from_bytes(
            video_bytes=mp4_bytes,
            caption=caption,
            cover_bytes=cover_image_bytes,
        )
        if media_id:
            print(f"Posted reel with ID: {media_id}")


__instance = None


def instagram_poster():
    global __instance
    if __instance is None:
        __instance = InstagramPoster()
    return __instance
