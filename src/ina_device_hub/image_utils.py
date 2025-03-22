import cv2
import numpy as np


class ImageUtils:
    @staticmethod
    def is_led_on_with_confidence(
        image_bytes: bytes,
        intensity_thresh: int = 245,  # 240〜250の間で試行
        min_bright_area_ratio: float = 0.0015,  # 0.001〜0.002の間で試行
        min_contour_area: int = 10,  # 輪郭の最小面積を少し大きめに
    ) -> tuple[bool, float]:
        """
        植物生育用LEDが点灯しているかを、輝度のしきい値と連続領域の大きさで判定する。
        点灯判定と、0.0〜1.0で表す信頼度を返す。
        """

        # 画像の読み込み
        image_array = np.asarray(bytearray(image_bytes), dtype=np.uint8)
        img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("画像の読み込みに失敗しました。")

        # ノイズ低減のためにガウシアンブラーを適用
        img_blurred = cv2.GaussianBlur(img, (5, 5), 0)

        # グレースケール変換
        gray = cv2.cvtColor(img_blurred, cv2.COLOR_BGR2GRAY)

        # 輝度の二値化
        _, thresh_img = cv2.threshold(gray, intensity_thresh, 255, cv2.THRESH_BINARY)

        # 輝度が高いピクセルの割合
        bright_pixels = np.count_nonzero(thresh_img)
        total_pixels = thresh_img.size
        bright_ratio = bright_pixels / total_pixels

        # 明るい領域（輪郭）の最大面積を求める
        contours, _ = cv2.findContours(thresh_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        max_area = 0
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > max_area:
                max_area = area

        # LED点灯とみなす条件:
        # - 画像全体に占める極端に明るい領域の割合が閾値を超える
        # - かつ、最大輪郭面積が一定以上 (min_contour_area)
        is_on = (bright_ratio > min_bright_area_ratio) and (max_area > min_contour_area)

        # 信頼度計算: 明るいピクセル割合を基準に0.0〜1.0で正規化
        confidence = bright_ratio / (min_bright_area_ratio * 2)
        if max_area <= min_contour_area:
            # 最大面積が極端に小さい場合は信頼度を下げる
            confidence *= 0.5

        # 0〜1.0にクリップ
        confidence = max(0.0, min(confidence, 1.0))

        return is_on, round(confidence, 3)


if __name__ == "__main__":
    img_path = "./.idea/sample.jpg"
    with open(img_path, "rb") as f:
        image_bytes = f.read()

    is_on, confidence = ImageUtils.is_led_on_with_confidence(image_bytes)
    print(f"LED点灯: {is_on}, 信頼度: {confidence}")
