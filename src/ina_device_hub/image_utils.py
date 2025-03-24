import os
import sys


class ImageUtils:
    @staticmethod
    def is_led_on_with_confidence(
        image_bytes: bytes,
        # --- グレースケールによる判定パラメータ ---
        intensity_thresh: int = 240,  # 240～250あたりで要調整
        min_bright_area_ratio: float = 0.001,  # 0.001～0.002あたりで要調整
        min_contour_area: int = 5,  # 輪郭の最小面積
        min_circularity: float = 0.6,  # LEDらしさを示す円形性の閾値
        # 追加: アルミホイル反射とみなすための閾値（画像全体に対する最大明る領域の割合）
        foil_reflection_area_thresh: float = 0.05,
        # --- カラー判定パラメータ ---
        color_ranges=(
            # (H_min, S_min, V_min, H_max, S_max, V_max)
            (160, 60, 60, 179, 255, 255),  # 赤系～ピンク
            (0, 60, 60, 10, 255, 255),  # 赤系(下限H)
            (100, 60, 60, 140, 255, 255),  # 青～紫寄り
            (35, 60, 60, 85, 255, 255),  # 緑系
        ),
        color_ratio_thresh: float = 0.01,  # マスク領域が画像全体の1%超なら点灯とみなす
        # --- 全体的なピンク・紫の飽和状態を除外するパラメータ ---
        pink_purple_hue_min: int = 130,
        pink_purple_hue_max: int = 170,
        pink_purple_saturation_min: int = 60,
        pink_purple_value_min: int = 60,
        # 変更: 0.8 → 0.9 にして飽和判定をやや緩く
        pink_purple_ratio_thresh: float = 0.99,
        # --- 色多様性（色偏り）判定のパラメータ ---
        # 変更: 15 → 10 にして色偏り判定をやや緩く
        color_bias_hue_std_thresh: float = 10,
    ) -> tuple[bool, float]:
        """
        植物育成用LEDの点灯状態を、以下の要素から判定します。

        1. 全体がピンク・紫で飽和している場合は誤検出防止のため False を返す。
           (pink_purple_ratio_thresh 以上なら飽和とみなす)
        2. 画像全体の色分布（Hueの標準偏差）が低い（color_bias_hue_std_thresh未満）場合は
           色偏りが強いとみなし、LED非照射と判定する。
        3. グレースケールによる高輝度の点光源検出
        4. アルミホイル上での大きな明る領域（反射）の検出
        5. カラー(HSV)判定

        これらを総合してLED点灯 (True/False) と信頼度を返す。
        """
        import cv2
        import numpy as np

        # --- 画像の読み込み ---
        image_array = np.asarray(bytearray(image_bytes), dtype=np.uint8)
        img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("画像の読み込みに失敗しました。")

        # --- ノイズ低減のためにガウシアンブラーを適用 ---
        img_blurred = cv2.GaussianBlur(img, (5, 5), 0)
        height, width, _ = img_blurred.shape
        total_pixels = height * width

        # ===================================================
        # (A) 全体がピンク・紫で飽和しているかの判定
        # ===================================================
        hsv = cv2.cvtColor(img_blurred, cv2.COLOR_BGR2HSV)
        pink_purple_mask = cv2.inRange(hsv, (pink_purple_hue_min, pink_purple_saturation_min, pink_purple_value_min), (pink_purple_hue_max, 255, 255))
        pink_purple_pixels = np.count_nonzero(pink_purple_mask)
        pink_purple_ratio = pink_purple_pixels / total_pixels
        if pink_purple_ratio > pink_purple_ratio_thresh:
            # 全体がピンク・紫で飽和しているとみなす
            return False, 0.0

        # ===================================================
        # (B) 色多様性（色偏り）の判定
        # ===================================================
        # Hueチャンネルの標準偏差が低いほど一色に偏っている
        hue_channel = hsv[:, :, 0].astype(np.float32)
        hue_std = np.std(hue_channel)
        if hue_std < color_bias_hue_std_thresh:
            # 色の多様性が低い（色偏りが強い）とみなす
            return False, 0.0

        # ===================================================
        # (1) グレースケールによる高輝度判定
        # ===================================================
        gray = cv2.cvtColor(img_blurred, cv2.COLOR_BGR2GRAY)
        _, thresh_img = cv2.threshold(gray, intensity_thresh, 255, cv2.THRESH_BINARY)
        bright_pixels = np.count_nonzero(thresh_img)
        bright_ratio = bright_pixels / total_pixels

        contours, _ = cv2.findContours(thresh_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        max_area = max((cv2.contourArea(cnt) for cnt in contours), default=0)

        if contours:
            best_contour = max(contours, key=cv2.contourArea)
            perimeter = cv2.arcLength(best_contour, True)
            circularity = 4 * np.pi * cv2.contourArea(best_contour) / (perimeter**2) if perimeter > 0 else 0
        else:
            circularity = 0

        is_on_gray = (bright_ratio > min_bright_area_ratio) and (max_area > min_contour_area) and (circularity >= min_circularity)

        # ===================================================
        # (2) アルミホイル反射の検出
        # ===================================================
        # 画像全体に対して最大明る領域の割合が一定以上であれば反射とみなし、
        # LEDが点灯している可能性を高める材料とする。
        foil_reflection_detected = (max_area / total_pixels) > foil_reflection_area_thresh

        # ===================================================
        # (3) カラー(Hue, Saturation, Value)情報による判定
        # ===================================================
        combined_mask = np.zeros_like(hsv[:, :, 0], dtype=np.uint8)
        for h_min, s_min, v_min, h_max, s_max, v_max in color_ranges:
            mask = cv2.inRange(hsv, (h_min, s_min, v_min), (h_max, s_max, v_max))
            combined_mask = cv2.bitwise_or(combined_mask, mask)
        color_pixels = np.count_nonzero(combined_mask)
        color_ratio = color_pixels / total_pixels
        is_on_color = color_ratio > color_ratio_thresh

        # ===================================================
        # (4) 統合判定
        # ===================================================
        # グレースケール or カラー or アルミホイル反射のいずれかが
        # LED点灯を示していればTrue
        is_on = is_on_gray or is_on_color or foil_reflection_detected

        # ===================================================
        # (5) 信頼度の計算（簡易例）
        # ===================================================
        raw_conf = 0.0
        if is_on_gray:
            raw_conf += bright_ratio / (min_bright_area_ratio * 2)
        if is_on_color:
            raw_conf += color_ratio / (color_ratio_thresh * 2)
        if foil_reflection_detected:
            raw_conf += (max_area / total_pixels) / (foil_reflection_area_thresh * 2)

        confidence = max(0.0, min(raw_conf, 1.0))

        return is_on, round(confidence, 3)


if __name__ == "__main__":
    args = sys.argv
    if len(args) != 2:
        print("Usage: python image_utils.py [画像ファイルパス|ディレクトリパス]")
        sys.exit(1)

    arg_img_pathe = args[1]

    # is directory
    if os.path.isdir(arg_img_pathe):
        img_pathes = [os.path.join(arg_img_pathe, f) for f in os.listdir(arg_img_pathe)]
    else:
        img_pathes = [arg_img_pathe]

    for img_path in img_pathes:
        if not os.path.exists(img_path):
            print(f"Error: {img_path} does not exist.")
            continue
        with open(img_path, "rb") as f:
            image_bytes = f.read()

        is_on, confidence = ImageUtils.is_led_on_with_confidence(image_bytes)
        print(f"{img_path} LED点灯: {is_on}, 信頼度: {confidence}")
