import os

from ina_device_hub.data_processor import DataProcessor
from ina_device_hub.hub_mqtt_client import HubMQTTClient
from ina_device_hub.timelapse_task import timelapse_task
from ina_device_hub.setting import setting


def run():
    data_processor = DataProcessor()
    hub_mqtt_client = HubMQTTClient(data_processor.sensor_data_queue)
    hub_mqtt_client.connect_mqtt()
    hub_mqtt_client.subscribe("sensor/+/#")

    # メッセージ処理用のワーカースレッドを開始
    data_processor.start()

    # timelapse task
    timelapse_task().start()

    # MQTTクライアントを開始(ブロッキング)
    hub_mqtt_client.loop()


if __name__ == "__main__":
    setting().settings["turso"]["local_db_path"] = os.path.join(os.path.expanduser(setting().get_work_dir()), "ina_serve.db")
    run()
