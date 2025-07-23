import json
import requests
from ina_device_hub.setting import setting


class Notification:
    def __init__(self):
        pass

    @staticmethod
    def send_discord_message(message: str):
        data = {"content": message}

        headers = {"Content-Type": "application/json"}

        response = requests.post(setting().get("notification")["discord_webhook_url"], headers=headers, data=json.dumps(data))

        if response.status_code == 204:
            print("Message sent successfully.")
        else:
            print(f"Failed to send message. Status code: {response.status_code}, Response: {response.text}")

    @staticmethod
    def send_discord_message_with_image(message, image_bytes, filename="image.png"):
        data = {"content": message}

        # 画像データをファイルとしてアップロードする準備
        files = {"file": (filename, image_bytes, "image/png")}

        # Webhookに画像を送信
        response = requests.post(setting().get("notification")["discord_webhook_url"], data=data, files=files)

        if 200 <= response.status_code < 300:
            print("スクリーンショットが送信されました")
        else:
            print(f"エラーが発生しました: {response.status_code}")


if __name__ == "__main__":
    # Example usage
    Notification.send_discord_message("Hello, this is a test message from INA Device Hub!")
    # You can replace the message with any string you want to send to Discord.
