from datetime import datetime, timezone, UTC
import sys
import os
import json
import uuid

from ina_device_hub.ina_db_connector import ina_db_connector
from ina_device_hub.ai_connector import ai_connector
from ina_device_hub.camera_device_repository import camera_device_repository
from ina_device_hub.camera_image_repository import camera_image_repository
from ina_device_hub.setting import setting


class InaAgent:
    image_analyze_system_prompt = """
    You are a professional agricultural engineer who is analyzing the image below.
    Please write a detailed analysis of the image.
    """
    evaluate_system_prompt = """
    You are a professional agricultural engineer who is evaluating the sensor data and describing the image below.
    Evaluate Guideline:
    - Image is summary. Please focus on the sensor data.
      (if you want to know more about the crops, please ask)

    OUTPUT:
    1. evaluation title
    2. Summary of the evaluation.
    3. If you want to know more about the crops, please ask.
    4. Actions to be taken by the system.
    5. Actions to be taken by the human.
    6. Additional information.
    """

    def __init__(self):
        self.ina_db_connector = ina_db_connector()
        self.camera_device_repository = camera_device_repository()
        self.camera_image_repository = camera_image_repository()
        self.setting = setting()
        self.ai_connector = ai_connector()

    def evaluate(self, location_id: str, target_date: datetime):
        yyyymmdd = target_date.strftime("%Y%m%d")
        __input_data = {}
        # get all sensors in location
        sensors = self.ina_db_connector.fetch_sensors_by_location_id(location_id)
        if not sensors:
            raise Exception("No sensors found")

        # get all sensor data
        for sensor in sensors:
            sensor_id = sensor[0]
            sensor_data = self.ina_db_connector.fetch_aggregated_sensor_data_by_daily(sensor_id, yyyymmdd)
            if not sensor_data:
                continue

            __input_data[sensor_id] = sensor_data

        # fetch camera image
        image_dict = self.camera_image_repository.get_date_image_by_location(
            target_date.replace(hour=14, minute=0, second=0, microsecond=0), location_id=location_id
        )

        # choose one image
        target_img = None
        for sensor_id, images in image_dict.items():
            if images:
                target_img = images[0]
                break

        if target_img is None:
            raise Exception("No image found")

        describe_result = self.ai_connector.analyze_image(
            target_img,
            system_prompt=self.image_analyze_system_prompt,
        )
        if describe_result is None:
            raise Exception("Failed to analyze image by AI")

        __input_data["image"] = describe_result

        # evaluate
        result = self.ai_connector.analyze_text(__input_data, system_prompt=self.evaluate_system_prompt)
        if result is None:
            raise Exception("Failed to evaluate by AI")

        # save result
        self.ina_db_connector.upsert_evaluation_result(location_id, __input_data, result)


if __name__ == "__main__":
    agent = InaAgent()
    agent.evaluate(None, datetime.now(UTC))
