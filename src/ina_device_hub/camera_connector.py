import ffmpeg

from ina_device_hub.camera_device_repository import camera_device_repository
from ina_device_hub.general_log import logger


class CameraConnector:
    def __init__(self):
        self.camera_device_repository = camera_device_repository()

    def take_picture(self, device_id: str):
        rtsp_url = self.construct_rtsp_url(device_id)
        if not rtsp_url:
            return None

        # take picture
        try:
            # RTSP の入力を受け取り、出力先をパイプに設定。
            # format='image2' で画像出力、vframes=1 で1フレームのみ取得
            img_bytes, _ = (
                ffmpeg.input(rtsp_url, rtsp_transport="tcp")
                .output("pipe:", format="image2", vframes=1)
                .run(capture_stdout=True, capture_stderr=True)
            )
            if not img_bytes:
                logger.error(f"Failed to take picture: {device_id}")
                return None

            return img_bytes  # バイト列として画像データが返される
        except ffmpeg.Error as e:
            logger.error("エラーが発生しました:"
                         f"{e.stderr.decode()}")
            return None

    def stream_rtsp(self, device_id: str):
        rtsp_url = self.construct_rtsp_url(device_id)
        if not rtsp_url:
            return None
        logger.info(f"Starting RTSP stream from {device_id}")
        # ffmpeg プロセスを非同期実行（MJPEG 形式で出力）
        process = (
            ffmpeg.input(rtsp_url, rtsp_transport="tcp")
            .output("pipe:", format="mjpeg", r=10)
            .run_async(pipe_stdout=True, pipe_stderr=True)
        )
        if process.poll() is not None:
            logger.error("Failed to start ffmpeg process")
            return

        logger.info(f"[{device_id}]Started ffmpeg process: PID={process.pid}")
        return process

    def stop_stream(self, device_id: str, process):
        if process.poll() is None:
            process.kill()
        process.wait()
        logger.info(f"[{device_id}]Stopped ffmpeg process: PID={process.pid}")
        process.stdout.close()

    def construct_rtsp_url(self, device_id: str):
        info = self.camera_device_repository.get(device_id)
        if not info:
            logger.error(f"Device not found: {device_id}")
            return None
        ip_address = info.get("ip_address")
        username = info.get("username")
        password = info.get("password")
        if not ip_address or not username or not password:
            logger.error(
                f"Invalid device info: ip_address={ip_address}, username={username}, password=[REDACTED]"
            )
            return None

        return self.get_rtsp_url(ip_address, username, password)

    @staticmethod
    def get_rtsp_url(ip_address: str, username: str, password: str):
        return f"rtsp://{username}:{password}@{ip_address}/stream1"

    @staticmethod
    def generate_frames(device_id):
        process = camera_connector().stream_rtsp(device_id)
        if process is None:
            return

        buffer = b""
        try:
            while True:
                chunk = process.stdout.read(1024)
                if not chunk:
                    break
                buffer += chunk
                while True:
                    start = buffer.find(b"\xff\xd8")
                    end = buffer.find(b"\xff\xd9")
                    if start != -1 and end != -1 and end > start:
                        frame = buffer[start : end + 2]
                        buffer = buffer[end + 2 :]
                        yield (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                        )
                    else:
                        break
        except GeneratorExit:
            logger.info(
                f"[{device_id}]Rtsp client disconnected. Stopping ffmpeg process"
            )
        except Exception as e:
            logger.error(f"Error: {e}")
            raise
        finally:
            camera_connector().stop_stream(device_id, process)


__instance = None


def camera_connector():
    global __instance
    if not __instance:
        __instance = CameraConnector()

    return __instance


if __name__ == "__main__":
    # example
    device_id = "INACD-a0b189d8-d789-4087-96d9-db91ecaf25c0"
    camera = camera_connector()
    img_bytes = camera.take_picture(device_id)
    if img_bytes:
        with open("image.jpg", "wb") as f:
            f.write(img_bytes)
    else:
        logger.error("Failed to take picture")
