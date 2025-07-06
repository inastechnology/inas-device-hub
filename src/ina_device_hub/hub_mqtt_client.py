import re
import threading
from paho.mqtt import client as mqtt_client

from ina_device_hub.setting import setting


client_id = setting().get("mqtt")["mqtt_client_id"]


class HubMQTTClient:
    def __init__(self, subscribed_data_queue):
        self.subscribed_data_queue = subscribed_data_queue

    def start(self):
        worker_thread = threading.Thread(target=self.client.loop_forever)
        worker_thread.daemon = True
        worker_thread.start()
        print("MQTT Client started")
        return worker_thread

    def loop(self):
        print("MQTT Client starting...")
        self.client.loop_forever()

    def connect_mqtt(self) -> None:
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                print("Connected to MQTT Broker!")
            else:
                print("Failed to connect, return code %d\n", rc)

        client = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION1, client_id)
        client.on_connect = on_connect
        print(f"Connecting to MQTT Broker {setting().get('mqtt')['mqtt_broker']}:{setting().get('mqtt')['mqtt_port']}")
        client.connect(setting().get("mqtt")["mqtt_broker"], setting().get("mqtt")["mqtt_port"])
        self.client = client

    def publish(self, client: mqtt_client.Client, topic: str, msg: str):
        result = client.publish(topic, msg)
        status = result[0]
        if status == 0:
            print(f"Send `{msg}` to topic `{topic}`")
        else:
            print(f"Failed to send message to topic {topic}")

    def subscribe(self):
        # Subscribe to sensor data topics
        def on_message(client, userdata, msg):
            omitted_payload = f"{msg.payload[0:100]}..." if len(msg.payload) > 100 else msg.payload
            print(f"Received `{omitted_payload}` from `{msg.topic}` topic")
            topic_parts = msg.topic.split("/")
            # topic matchers
            # TOPIC: sensor/{sensor_id}/status/{seqId}
            if re.match(r"^sensor/[^/]+/(status|image|audio)/[^/]+$", msg.topic):
                # Extract sensor_id, kind, and seqId from the topic
                # トピックの形式: sensor/{sensor_id}/{kind}/{seqId}
                sensor_id = topic_parts[1] if len(topic_parts) > 1 else None
                kind = topic_parts[2] if len(topic_parts) > 2 else None
                seqId = topic_parts[3] if len(topic_parts) > 3 else None
                if sensor_id is not None and kind is not None:
                    self.subscribed_data_queue.put(
                        {
                            "sensor_id": sensor_id,
                            "kind": kind,
                            "payload": msg.payload,
                            "seqId": seqId,
                        }
                    )
                else:
                    print("Invalid topic")
            # elif re.match(r"^sensor/[^/]+/control/taskreq/\d+$", msg.topic):
            #     # Extract sensor_id and seqId from the topic
            #     # トピックの形式: sensor/{sensor_id}/control/taskreq/{seqId}
            #     if (
            #         len(topic_parts) == 4
            #         and topic_parts[0] == "sensor"
            #         and topic_parts[1]
            #         and topic_parts[2] == "taskreq"
            #         and topic_parts[3].isdigit()  # seqId should be a number
            #     ):
            #         sensor_id = topic_parts[1]
            #         seqId = topic_parts[3]
            #         # TODO: タスク一覧を生成し、センサーに通知する
            #         # taskList = self.task_manager.get_task_list(sensor_id)
            #         taskListAsHex = "0102030405060708"  # Example task list in HEX format
            #         print(f"Received task request from sensor {sensor_id} with seqId {seqId}")
            #         print(f"Task list to send: {taskListAsHex}")
            #         # Here you would publish the task list back to the sensor
            #         # self.publish(
            #         #     client,
            #         #     f"sensor/{sensor_id}/control/taskreq/{seqId}",
            #         #     taskListAsHex
            #         # )
            #     else:
            #         print(f"ur Invalid task topic: {msg.topic}")

        self._subscribe("sensor/+/#", on_message=on_message)
        # self._subscribe("sensor/+/control/taskreq/+", on_message=on_message)

    def _subscribe(self, topic: str, on_message):
        self.client.subscribe(topic, qos=1)
        self.client.on_message = on_message
        print(f"Subscribed to topic `{topic}`")
