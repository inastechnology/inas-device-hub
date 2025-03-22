import time
import queue
import json
import threading
from datetime import datetime, timezone

from ina_device_hub.sensor_device_repository import sensor_device_repository
from ina_device_hub.sensor_data_repository import sensor_data_repository
from ina_device_hub.sensor_image_repogitory import sensor_image_repogitory
from ina_device_hub.sensor_data_queue import SensorDataQueue
from ina_device_hub.ina_db_connector import ina_db_connector
from ina_device_hub.general_log import logger
from ina_device_hub.setting import setting


class DataProcessor:

    def __init__(self):
        self.sensor_data_queue = SensorDataQueue()
        self.sensor_device_repository = sensor_device_repository()
        self.sensor_data_repository = sensor_data_repository()
        self.sensor_image_repogitory = sensor_image_repogitory()
        self.image_buffer = {}
        self.audio_buffer = {}

    def start(self):
        worker_thread = threading.Thread(target=self.process)
        worker_thread.daemon = True
        worker_thread.start()

    def process(self):
        while True:
            try:
                # queue からメッセージを取得
                message = self.sensor_data_queue.get()
                self.sensor_device_repository.add(
                    message["sensor_id"],
                    {
                        "name": message["sensor_id"],
                        "type": message["sensor_id"].split("-")[0],
                        "detected_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                    },
                )

                # ここでメッセージの処理を実施
                if message["kind"] == "status":
                    self.process_sensor_data(
                        message["sensor_id"],
                        message["kind"],
                        message["payload"],
                        message["seqId"],
                    )

                elif message["kind"] == "image":
                    self.process_sensor_image(
                        message["sensor_id"],
                        message["kind"],
                        message["payload"],
                        message["seqId"],
                    )
                elif message["kind"] == "audio":
                    # TODO: Implement audio processing
                    pass
                else:
                    # 規定外のメッセージの場合はログ出力
                    logger.error(
                        f"Device {message['sensor_id']} sensor data: {message['payload']}"
                    )
                # キューからメッセージを取り出し完了
                self.sensor_data_queue.task_done()
            except queue.Empty:
                # キューが空の場合は何もしない
                time.sleep(1)
                continue
            except Exception as e:
                logger.exception(e)

                time.sleep(1)
                continue

    def process_sensor_data(self, sensor_id, kind, payload, seqId):
        """
        Parse sensor data payload
        Args:
            sensor_id (str): device id
            kind (str): message kind
            payload (str): message payload
                json string - sensor data
            seqId (int): sequence id
        """
        # バイト列の場合は文字列に変換
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        logger.debug(f"Device {sensor_id} sensor data: {payload}")

        # 文字列から辞書型に変換
        payload_as_dict = json.loads(payload)

        self.sensor_data_repository.add(sensor_id, seqId, payload_as_dict)

    def process_sensor_image(self, sensor_id, kind, payload, seqId):
        """
        Parse image payload
        Args:
            sensor_id (str): device id
            kind (str): message kind
            payload (str): message payload
                json string - image info. first received data
                binary data - image fragments
            seqId (int): sequence id
        @note
        1. receive image info(json data)
        2. receive image fragments...
        """

        if setting().get("sensor").get("save_image") is False:
            return  # do nothing

        try:
            # check whether payload is image info or not
            payload = json.loads(payload)
            image_size = payload["size"]
            # add image data to buffer
            if sensor_id not in self.image_buffer:
                self.image_buffer[sensor_id] = {}

            self.image_buffer[sensor_id] = dict()
            self.image_buffer[sensor_id][seqId] = {
                "size": image_size,
                "image": bytearray(),
            }
            return
        except json.JSONDecodeError:
            pass
        except UnicodeDecodeError:
            pass

        if seqId not in self.image_buffer[sensor_id]:
            logger.error(f"[{sensor_id}:{seqId}] image info not found")
            return

        image_fragment = bytearray(payload)

        self.image_buffer[sensor_id][seqId]["image"].extend(image_fragment)
        # check whether all image data received
        if (
            len(self.image_buffer[sensor_id][seqId]["image"])
            >= self.image_buffer[sensor_id][seqId]["size"]
        ):
            # all image data received
            logger.debug(f"[{sensor_id}:{seqId}] all image data received")
            # all image data received
            image_data = self.image_buffer[sensor_id][seqId]["image"].copy()
            del self.image_buffer[sensor_id][seqId]
            # save image data
            self.sensor_image_repogitory.save(sensor_id, image_data)

    def process_sensor_audio(self, sensor_id, kind, payload, seqId):
        """
        Parse audio payload
        1. receive audio info(json data) including audio data counts
        2. receive audio fragments...count times
        """
        try:
            payload = json.loads(payload)
            audio_count = payload["count"]
            # add audio data to buffer
            if sensor_id not in self.audio_buffer:
                self.audio_buffer[sensor_id] = {}

            self.audio_buffer[sensor_id] = dict()
            self.audio_buffer[sensor_id][seqId] = {
                "count": 0,
                "all_count": audio_count,
                "audio": bytearray(),
            }
            return
        except json.JSONDecodeError:
            pass
        except UnicodeDecodeError:
            pass

        if seqId not in self.audio_buffer[sensor_id]:
            logger.error(f"[{sensor_id}:{seqId}] audio info not found")
            return

        audio_fragment = bytearray(payload)

        self.audio_buffer[sensor_id][seqId]["audio"].extend(audio_fragment)
        self.audio_buffer[sensor_id][seqId]["count"] += 1
        # check whether all audio data received
        if (
            self.audio_buffer[sensor_id][seqId]["count"]
            >= self.audio_buffer[sensor_id][seqId]["all_count"]
        ):
            # all audio data received
            logger.debug(f"[{sensor_id}:{seqId}] all audio data received")
            # all audio data received
            audio_data = self.audio_buffer[sensor_id][seqId]["audio"].copy()
            del self.audio_buffer[sensor_id][seqId]
            # save audio data
            # self.sensor_audio_repogitory.save(sensor_id, audio_data)
