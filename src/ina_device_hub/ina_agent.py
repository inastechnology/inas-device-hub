import os
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from flask import json

from ina_device_hub.ai_connector import ai_connector
from ina_device_hub.camera_device_repository import camera_device_repository
from ina_device_hub.camera_image_repository import camera_image_repository
from ina_device_hub.general_log import logger
from ina_device_hub.ina_db_connector import ina_db_connector
from ina_device_hub.location_repository import location_repository
from ina_device_hub.setting import setting


class InaAgent:
    image_analyze_system_prompt = """
Image Description Prompt for Assessing Plant Growth Conditions
The following image shows the current state of plant growth. Please describe the image in detail and objectively in English, focusing specifically on plant health, growth conditions, and signs of environmental stress (e.g., changes in leaf color, wilting, disease, pest infestations, etc.). Be sure to address the following points clearly:

- Leaf color and condition (e.g., deep or pale green, presence of yellowing or browning)
- Leaf and stem structure and density (e.g., drooping of leaves, stem thickness and sturdiness)
- Signs of diseases or pest infestations (e.g., leaf spots, insect damage, discoloration)
- Overall growth condition (e.g., vitality, stunted growth, excessive growth)
- Other anomalies or noticeable issues visible in the image

Your detailed description will serve as critical input for an AI agent to accurately assess the plant's growth state. Please ensure your observations are precise, detailed, and objective.
    """

    evaluate_system_prompt = """
🌱 Plant Growth Condition Summary Report
Analyze the provided sensor data and image description to deliver a clear, user-friendly evaluation of the plant’s current growth condition. Ensure your report is concise, informative, and visually appealing. Provide insights in the following structured format:

🌿 Overall Plant Health: (Brief summary of current health status and vigor.)
⚠️ Potential Issues: (Clearly highlight any detected problems such as nutrient deficiencies, water stress, disease symptoms, pest activity, or environmental stress.)
✅ Recommended Actions: (Suggest practical, actionable steps to address any identified issues and optimize plant health.)

Make your evaluation insightful and attractive for users, supporting effective decision-making and engagement.
    """

    def __init__(self):
        self.ina_db_connector = ina_db_connector()
        self.location_repository = location_repository()
        self.camera_device_repository = camera_device_repository()
        self.camera_image_repository = camera_image_repository()
        self.setting = setting()
        self.ai_connector = ai_connector()
        self.routin_scheduler = BackgroundScheduler()

    def start(self):
        # set scheduler at start time
        schedule_setting = self.setting.get("ai")["schedule"]["start"]
        logger.info(f"Start AI agent at {schedule_setting}")
        local_target_time = datetime.strptime(schedule_setting, "%H:%M")
        self.routin_scheduler.add_job(
            self.routine,
            "cron",
            hour=local_target_time.hour,
            minute=local_target_time.minute,
            second=local_target_time.second,
        )

    def routine(self):
        # get all locations
        locations = self.location_repository.get_all()
        if not locations:
            raise Exception("No locations found")

        for location in locations:
            location_id = location[0]
            yesterday = datetime.now(UTC) - timedelta(days=1)
            self.evaluate(location_id, yesterday)

    def evaluate(self, location_id: str, target_date: datetime):
        yyyymmdd = target_date.strftime("%Y%m%d")
        __input_data = {}
        # get all sensors in location
        sensors = self.ina_db_connector.fetch_sensors_by_location_id(location_id)
        if not sensors:
            raise Exception("No sensors found")

        # get all sensor data
        __input_data["sensor_data"] = {}
        for sensor in sensors:
            sensor_id = sensor[0]
            sensor_data = self.ina_db_connector.fetch_aggregated_sensor_data_by_daily(sensor_id, yyyymmdd)
            if not sensor_data:
                continue

            # filter invalid data
            input_sensor_data = []
            for elem in sensor_data:
                try:
                    extra = json.loads(elem[11]) if elem[11] else {}
                except Exception as e:
                    extra = {}
                data_as_dict = {
                    "temp": elem[1] if elem[1] > -1000 else None,
                    "tds": elem[2] if elem[2] > -1000 else None,
                    "ec": elem[3] if elem[3] > -1000 else None,
                    "ph": elem[4] if elem[4] > -1000 else None,
                    "dissolved_oxygen": elem[5] if elem[5] > -1000 else None,
                    "ammonia": elem[6] if elem[6] > -1000 else None,
                    "nitrate": elem[7] if elem[7] > -1000 else None,
                    "created_at": elem[10],
                    "extra": extra,
                }
                input_sensor_data.append(data_as_dict)
            __input_data["sensor_data"][sensor_id] = input_sensor_data

        # fetch camera image
        date_filter = target_date.replace(hour=5, minute=0, second=0, microsecond=0).strftime("%Y%m%d/%Y%m%d_%H")
        image_dict = self.camera_image_repository.get_date_image_by_location(date_filter, location_id=location_id)

        # choose one image
        target_img = None
        for sensor_id, images in image_dict.items():
            if images:
                target_img = images[0]
                break

        if target_img is None:
            raise Exception("No image found")

        # download image
        target_img_as_bytes = self.camera_image_repository.download_image(target_img["key"])

        # save as test
        with open("test.jpg", "wb") as f:
            f.write(target_img_as_bytes)

        describe_result = self.ai_connector.analyze_image(
            target_img_as_bytes,
            system_prompt=self.image_analyze_system_prompt,
            max_tokens=512,
        )
        if describe_result is None:
            raise Exception("Failed to analyze image by AI")
        print(describe_result)
        __input_data["image"] = describe_result

        # evaluate
        input_str = json.dumps(__input_data)
        message = f"""
        Please evaluate the location {location_id} with the following data.(please output language:{setting().get("language")})
        Input data:
        {input_str}
        """
        result = self.ai_connector.analyze_text(message, system_prompt=self.evaluate_system_prompt)
        if result is None:
            raise Exception("Failed to evaluate by AI")

        logger.info(
            f"""***🌟
Location {location_id} evaluated successfully
INPUT:
{input_str}
====
OUTPUT:
{result}
"""
        )
        # save result
        self.ina_db_connector.upsert_evaluation_result(location_id, input_str, result)


__instance = None


def ina_agent():
    global __instance
    if not __instance:
        __instance = InaAgent()

    return __instance


if __name__ == "__main__":
    setting().settings["turso"]["local_db_path"] = os.path.join(os.path.expanduser(setting().get_work_dir()), ".test.db")
    agent = InaAgent()
    yesterday = datetime.now(UTC) - timedelta(days=1)
    agent.evaluate(None, yesterday)
