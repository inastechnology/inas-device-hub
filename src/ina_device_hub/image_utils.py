import cv2
import numpy as np


class ImageUtils:
    @staticmethod
    def is_led_on_with_confidence(image_bytes: bytes, threshold_ratio: float = 0.005) -> tuple[bool, float]:
        """
        LED点灯の有無を判定し、信頼度スコアを返す。

        Args:
            image_bytes (bytes): 画像ファイルのバイトデータ
            threshold_ratio (float): 点灯と判定するピクセル比率の閾値（デフォルト: 0.5%）

        Returns:
            Tuple[bool, float]: (LEDが点灯しているか, 信頼度スコア[0.0〜1.0])
        """
        # 画像bytesからOpenCV画像に変換
        image_array = np.asarray(bytearray(image_bytes), dtype=np.uint8)
        img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

        if img is None:
            raise ValueError("画像の読み込みに失敗しました。")

        # HSVに変換
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # 紫～青の色域（必要に応じて調整）
        lower_purple = np.array([110, 50, 50])
        upper_purple = np.array([160, 255, 255])
        mask = cv2.inRange(hsv, lower_purple, upper_purple)

        # ピクセル数をカウント
        total_pixels = mask.size
        detected_pixels = np.count_nonzero(mask)
        detected_ratio = detected_pixels / total_pixels

        # 判定と信頼度
        is_on = detected_ratio > threshold_ratio
        confidence = min(detected_ratio / threshold_ratio, 1.0) if is_on else 1.0 - detected_ratio / threshold_ratio

        return is_on, round(confidence, 3)


if __name__ == "__main__":
    with open("dark.jpg", "rb") as f:
        image_bytes = f.read()

    is_on, confidence = ImageUtils.is_led_on_with_confidence(image_bytes)
    print(f"LED点灯: {is_on}, 信頼度: {confidence}")
