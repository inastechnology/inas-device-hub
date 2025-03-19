from ina_device_hub import web_server as web_server
from ina_device_hub.data_processor import DataProcessor
from ina_device_hub.hub_mqtt_client import HubMQTTClient
from ina_device_hub.timelapse_task import timelapse_task


def run():
    data_processor = DataProcessor()
    hub_mqtt_client = HubMQTTClient(data_processor.sensor_data_queue)
    hub_mqtt_client.connect_mqtt()
    hub_mqtt_client.subscribe("sensor/+/#")

    # メッセージ処理用のワーカースレッドを開始
    data_processor.start()

    # MQTTクライアントのワーカースレッドを開始
    hub_mqtt_client.start()

    # timelapse task
    timelapse_task().start()

    # Flaskサーバーを起動
    web_server.flask_run()


if __name__ == "__main__":
    run()
