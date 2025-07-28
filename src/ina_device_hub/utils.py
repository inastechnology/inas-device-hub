from io import BytesIO
import subprocess
import threading
from typing import Iterable
from PIL import Image

import kaleido
from plotly import graph_objs as go
from plotly.offline import plot
from plotly.subplots import make_subplots
from tqdm import tqdm
from PIL import Image, ImageDraw, ImageFont
import textwrap
import emoji

from ina_device_hub.general_log import logger


class Utils:
    @staticmethod
    def create_latest_aggregated_graph_as_html(sensor_id, latest_aggregated_data):
        return plot(Utils.__create_latest_aggregated_graph(sensor_id, latest_aggregated_data), output_type="div")

    @staticmethod
    def create_latest_aggregated_graph_as_image(sensor_id, latest_aggregated_data, image_format="webp"):
        fig = Utils.__create_latest_aggregated_graph(sensor_id, latest_aggregated_data)
        if fig is None:
            return None
        return fig.to_image(format=image_format)

    @staticmethod
    def __create_latest_aggregated_graph(sensor_id, latest_aggregated_data):
        if latest_aggregated_data is None:
            return None

        # construct data
        temp_x = []
        temp_y = []
        tds_x = []
        tds_y = []
        watering_x = []
        watering_y = []
        moisture_x = []
        moisture_y = []

        for data in latest_aggregated_data:
            if "temp" in data and data["temp"] != -1000:
                temp_x.append(data["yyyymmddhh"])
                temp_y.append(data["temp"])
            if "tds" in data and data["tds"] != -1000:
                tds_x.append(data["yyyymmddhh"])
                tds_y.append(data["tds"])
            if "extra" in data:
                if "max_watering_sec" in data["extra"] and data["extra"]["max_watering_sec"] is not None and data["extra"]["max_watering_sec"] > 0:
                    watering_x.append(data["created_at"].astimezone().strftime("%Y-%m-%d %H:%M:%S"))
                    watering_y.append(data["extra"]["max_watering_sec"])
                if "min_soil_moisture" in data["extra"] and data["extra"]["min_soil_moisture"] is not None and 0 < data["extra"]["min_soil_moisture"] < 100:
                    moisture_x.append(data["created_at"].astimezone().strftime("%Y-%m-%d %H:%M:%S"))
                    moisture_y.append(data["extra"]["min_soil_moisture"])

        _rows = 0
        _cols = 0
        current_row = 1
        current_col = 1
        is_exist_temp_tds = len(temp_x) > 0 and len(tds_x) > 0
        if is_exist_temp_tds:
            _rows += 1
            _cols += 2  # temp and tds

        is_exist_watering_moisture = (len(watering_x) > 0 and len(watering_y) > 0) or (len(moisture_x) > 0 and len(moisture_y) > 0)
        if is_exist_watering_moisture:
            _rows += 1
            _cols += 1  # watering and soil moisture in the same subplot
        fig = make_subplots(rows=_rows, cols=_cols)
        fig.update_layout(title="Latest Sensor Data")

        if is_exist_temp_tds:
            # temp
            temp = go.Scatter(x=temp_x, y=temp_y, mode="lines+markers", name="temp")
            fig.add_trace(temp, row=current_row, col=current_col)
            current_col += 1

            # tds
            tds = go.Scatter(x=tds_x, y=tds_y, mode="lines+markers", name="tds")
            fig.add_trace(tds, row=current_row, col=current_col)
            current_row += 1
            current_col = 1

        if is_exist_watering_moisture:
            # watering & soil moisture
            # watering is shown as bar chart
            watering = go.Bar(x=watering_x, y=watering_y, name="watering")
            # soil moisture is shown as line chart
            moisture = go.Scatter(x=moisture_x, y=moisture_y, mode="lines+markers", name="soil moisture", line=dict(color="green", width=2, dash="dash"))
            # overlay watering and soil moisture in the same subplot
            fig.add_trace(watering, row=current_row, col=current_col)
            fig.add_trace(moisture, row=current_row, col=current_col)

        # add layout h:480px
        fig.update_layout(height=480, template="plotly_white")

        return fig

    @staticmethod
    def jpeg_iterable_to_mp4_bytes(
        jpeg_sequence: Iterable[bytes],
        width: int = 1080,
        height: int = 1920,
        fps: int = 24,  # 出力FPS (総枚数 / 秒数)
    ) -> bytes:
        """
        JPEGバイト列の連続を ffmpeg にストリームし、fragmented MP4 を bytes で返す。
        音声ストリーム無し (必要なら -i bgm などを追加して下さい)
        """
        # ffmpeg がインストールされていることを確認
        check_cmd = ["ffmpeg", "-version"]
        try:
            subprocess.run(check_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            logger.error(f"ffmpeg is not installed or not found in PATH: {e}")
            raise RuntimeError("ffmpeg is required to convert JPEGs to MP4. Please install ffmpeg and ensure it is in your PATH.")
        # ffmpeg コマンドを組み立て
        cmd = [
            "ffmpeg",
            "-loglevel",
            "error",
            "-f",
            "image2pipe",
            "-framerate",
            str(fps),
            "-i",
            "-",  # stdin
            "-vf",
            f"fps={fps},format=yuv420p,scale={width}:{height}:flags=lanczos",
            "-c:v",
            "libx264",
            "-profile:v",
            "high",
            "-level",
            "4.1",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "frag_keyframe+empty_moov",
            "-f",
            "mp4",
            "pipe:1",  # stdout
        ]

        logger.info(f"Encoding {len(jpeg_sequence)} JPEGs to MP4 with command: {' '.join(cmd)}")
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            # 受信スレッドを立ち上げる
            mp4_bytes = b""

            def _read_buffer():
                nonlocal mp4_bytes
                while True:
                    chunk = proc.stdout.read(1024 * 1024)
                    if not chunk:
                        break
                    mp4_bytes += chunk

            t = threading.Thread(target=_read_buffer, daemon=True)
            t.start()
            try:
                tqdm_iterable = tqdm(jpeg_sequence, desc="Encoding JPEGs to MP4", unit="JPEG")
                for jpg in tqdm_iterable:
                    proc.stdin.write(jpg)

                logger.info("Waiting for ffmpeg to finish...")
                # ffmpeg の終了を待つ
                proc.stdin.flush()
                proc.stdin.close()  # EOF

                t.join()  # スレッドの終了を待つ
            except Exception as e:
                logger.error(f"Error while writing to ffmpeg stdin: {e}")
                raise
            finally:
                proc.kill()  # ffmpeg プロセスを強制終了

            mp4_bytes = mp4_bytes.strip()
            if not mp4_bytes:
                raise ValueError("No MP4 bytes generated from JPEG sequence")
            return mp4_bytes
        finally:
            proc.kill()

    @staticmethod
    def crop_image(image_bytes: bytes, aspect_ratio: float):
        """
        画像を中央から指定アスペクト比 (W/H) でクロップして
        JPEG/PNG など元と同じフォーマットの bytes にして返す。

        Parameters
        ----------
        image_bytes : bytes
            入力画像データ
        aspect_ratio : float
            目標アスペクト比 (幅 ÷ 高さ)。例: 4:5 → 4/5

        Returns
        -------
        bytes
            クロップ後の画像バイト列
        """
        img = Image.open(BytesIO(image_bytes))
        w, h = img.size  # 現在の幅・高さ

        # 目標幅を算出 (高さはそのまま使う前提)
        target_w = int(h * aspect_ratio)

        if target_w > w:
            raise ValueError(f"元画像の幅({w})より目標幅({target_w})のほうが大きいのでクロップ不可")

        # 中央から左右をカット
        left = (w - target_w) // 2
        right = left + target_w
        cropped = img.crop((left, 0, right, h))  # (left, upper, right, lower)
        cropped_width, cropped_height = cropped.size

        # 同じフォーマットでバイト列へ
        buf = BytesIO()
        cropped.save(buf, format=img.format or "JPEG", quality=95)
        return buf.getvalue(), cropped_width, cropped_height

    @staticmethod
    def fit_text_to_box(draw, text, max_width, max_lines, font_path, max_font_size=96, min_font_size=20):
        print(f"Fitting text to box: max_width={max_width}, max_lines={max_lines}, font_path={font_path}")
        for font_size in range(max_font_size, min_font_size - 1, -2):
            font = ImageFont.truetype(font_path, font_size)
            wrapped = textwrap.wrap(text, width=100)  # 仮wrap
            lines = []
            for line in wrapped:
                current_line = ""
                for word in line.split():
                    test_line = current_line + (" " if current_line else "") + word
                    bbox = draw.textbbox((0, 0), test_line, font=font)
                    w = bbox[2] - bbox[0]

                    if w <= max_width:
                        current_line = test_line
                    else:
                        if current_line:
                            lines.append(current_line)
                        current_line = word
                if current_line:
                    lines.append(current_line)
                if len(lines) > max_lines:
                    break
            if len(lines) <= max_lines:
                return font, lines
        short_text = textwrap.shorten(text, width=30, placeholder="…")
        return ImageFont.truetype(font_path, min_font_size), [short_text]

    @staticmethod
    def draw_multiline_text_with_emoji(image, lines, font_main, font_emoji, box, fill="white", line_spacing=10):
        draw = ImageDraw.Draw(image)
        x0, y0, x1, y1 = box
        current_y = y0

        for line in lines:
            # 描画位置の中央揃えを決める
            text_width = sum(Utils.__get_text_size(font_main, char)[0] if ord(char) <= 0x1F000 else Utils.__get_text_size(font_emoji, char)[0] for char in line)
            current_x = (x1 + x0 - text_width) // 2

            for char in line:
                font = None
                if emoji.is_emoji(char):
                    font = font_emoji
                    print(f"Using emoji font for character: {char}")
                else:
                    font = font_main
                if font is None:
                    logger.warning(f"Font not found for character: {char}")
                    continue

                draw.text((current_x, current_y), char, font=font, fill=fill)
                char_width = Utils.__get_text_size(font, char)[0]
                current_x += char_width

            current_y += max(font_main.size, font_emoji.size) + line_spacing

    @staticmethod
    def add_text_overlay(image_bytes, text):
        font_main_path = "/home/mtan/.ina-device-hub/font/NotoSansJP-Regular.ttf"
        font_emoji_path = "/home/mtan/.ina-device-hub/font/NotoColorEmoji-Regular.ttf"
        text = Utils.remove_variation_selectors(text)
        image = Image.open(BytesIO(image_bytes))
        width, height = image.size
        draw = ImageDraw.Draw(image)

        box_margin_w = int(width * 0.05)
        box_width = width - box_margin_w * 2
        box_height = int(height * 0.3)
        box_bottom = height - int(height * 0.03)

        font_main, lines = Utils.fit_text_to_box(draw, text, box_width - 40, max_lines=2, font_path=font_main_path)

        # 背景ボックスサイズ
        line_height = Utils.__get_text_size(font_main, "A")[1]
        total_text_height = len(lines) * line_height + (len(lines) - 1) * 10
        box_top = box_bottom - total_text_height - 80  # 背景高さの調整幅を十分に取る

        radius = 30
        box_coords = (box_margin_w, box_top, width - box_margin_w, box_bottom)
        draw.rounded_rectangle(box_coords, radius=radius, fill=(0, 0, 0, 180))

        # 絵文字用フォント読み込み
        font_emoji = ImageFont.truetype(font_emoji_path, size=font_main.size)

        Utils.draw_multiline_text_with_emoji(image, lines, font_main, font_emoji, box_coords)
        ret_bytes = BytesIO()
        image.save(ret_bytes, format=image.format or "JPEG", quality=95)
        return ret_bytes.getvalue()

    @staticmethod
    def remove_variation_selectors(text: str) -> str:
        return "".join(c for c in text if ord(c) != 0xFE0F)

    @staticmethod
    def __get_text_size(font, text):
        bbox = font.getbbox(text)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        return width, height
