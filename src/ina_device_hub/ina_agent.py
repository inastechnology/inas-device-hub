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
from ina_device_hub.notification import Notification
from ina_device_hub.sensor_data_repository import sensor_data_repository
from ina_device_hub.sensor_device_repository import sensor_device_repository
from ina_device_hub.setting import setting
from ina_device_hub.utils import Utils


class InaAgent:
    image_analyze_system_prompt = """
Purpose:
    This system extracts observable features from a plant image and outputs a clear, concise text description to serve as foundational data for further evaluation.

Instructions:

Observational Items: Describe what you see regarding:
    - Leaf color, shape, and size
    - Stem condition
    - Presence of flowers or fruits
    - Overall balance and structure
    - Any visible abnormalities (e.g., discoloration, spots, wilting)

Rules for Description:
    - Only include information that is clearly visible in the image.
    - Do not infer or add supplementary details that are not present.
    - Use concise, straightforward language.

Usage:
    The output text will be combined with sensor data (e.g., hourly temperature, TDS levels, LED illumination status) and possibly a previous evaluation summary to assess the plant's growth status.
    """

    evaluate_system_prompt = """
Purpose:
    Integrate sensor values, text extracted from plant images, and, if available, a summary of previous evaluations to provide a user-friendly assessment of the plant’s growth status.

Instructions:
    Input Information:
        - Sensor values (e.g., hourly temperature, TDS, LED illumination on/off)
        - Text description generated from the plant image
        - (Optionally) A summary of the previous evaluation

    Evaluation Guidelines:
        - User-Friendly Language: Use warm, encouraging, and easy-to-understand language that makes the user feel positive and motivated.
        - Praise and Encouragement: Highlight positive aspects and improvements, congratulating the user when appropriate.
        - Specific, Actionable Advice: If issues are detected, offer clear, simple instructions for corrective action (e.g., "add liquid fertilizer" rather than technical targets like "adjust TDS to 800 ppm").
        - Data-Driven: Only comment on the data provided. Do not mention or speculate on information that is not present in the inputs.

Objective:
    Deliver an intuitive, supportive assessment that helps the user easily understand the plant’s current status and the necessary steps for improvement.
"""

    evaluate_summary_system_prompt = """
Purpose:
    This system extracts key insights from the current plant growth evaluation and reformats them into a concise summary. This summary will be integrated into the next evaluation to maintain continuity and provide context.

Instructions:

    Input:
        The complete text output from the current plant growth evaluation.

    Task:
        Analyze the evaluation text and identify the key points that should be carried forward for future reference.

    Key Elements to Extract:
        - Strengths: Note all positive observations and strong points regarding the plant’s health and growth.
        - Areas for Improvement: Identify any issues or observations that require attention.
        - Actionable Recommendations: Extract clear, simple advice that the user can implement (e.g., “add liquid fertilizer” rather than technical adjustments).

    Formatting Requirements:
        - Structure the summary under clearly labeled sections:
            - Strengths
            - Areas for Improvement
            - Actionable Recommendations

        - Use concise, straightforward language that reflects only the facts stated in the evaluation.
        - Do not add or infer new information beyond what is provided in the evaluation text.

    Output:
        The output should be a standardized summary that is easy to review and directly applicable as input for the next evaluation cycle.

Example:
    If the current evaluation notes that the plant is growing well overall but shows slight discoloration on some leaves, the summary might be:
        - Strengths: Overall healthy growth with vibrant leaves.
        - Areas for Improvement: Slight discoloration on some leaves.
        - Actionable Recommendations: Monitor leaf discoloration closely and adjust light exposure if needed.

Objective:
    Ensure the summary accurately captures the essential points of the evaluation, facilitating continuous, context-aware monitoring and feedback for the plant’s growth.
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
        logger.info(f"[INA AGENT]Set scheduler at {schedule_setting}")
        local_target_time = datetime.strptime(schedule_setting, "%H:%M")
        self.routin_scheduler.add_job(
            self.routine,
            "cron",
            hour=local_target_time.hour,
            minute=local_target_time.minute,
            second=local_target_time.second,
        )
        self.routin_scheduler.start()

    def routine(self):
        logger.info("[INA AGENT]Routine started")
        # get all locations
        location_dict = self.location_repository.get_all()
        try:
            if location_dict is None or len(location_dict) == 0:
                raise Exception("No locations found")

            for key, location in location_dict.items():
                location_id = key
                yesterday = datetime.now(UTC) - timedelta(days=1)
                self.evaluate(location_id, yesterday)
        except Exception as e:
            logger.exception(f"[INA AGENT]Routine failed: {e}")
        finally:
            logger.info("[INA AGENT]Routine finished")

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
        # TODO: choose the best image
        target_img = None
        target_img_as_bytes = None
        for sensor_id, images in image_dict.items():
            if images:
                target_img = images[0]
                break

        if target_img is not None:
            logger.info(f"Target image found: {target_img}")
            # download image
            target_img_as_bytes = self.camera_image_repository.download_image(target_img["key"])

            # save as test
            with open(os.path.join(setting().get_work_dir(), "evaluate.jpg"), "wb") as f:
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
        else:
            logger.info("No target image found")

        # fetch previous evaluation summary
        previous_evaluation = self.ina_db_connector.fetch_latest_evaluation_result(location_id)
        if previous_evaluation:
            # evaluation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            # location_id TEXT,
            # input_data TEXT,
            # output_data TEXT,
            # summary TEXT,
            # created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            summary = previous_evaluation[4]
            __input_data["previous_evaluation"] = {
                "created_at": previous_evaluation[5],
                "summary": summary,
            }

        # evaluate
        input_str = json.dumps(__input_data)
        message = f"""
        Please evaluate the location {location_id} with the following data.(please output language:{setting().get("language")})
        Input data:
        {input_str}
        """
        evaluate_result = self.ai_connector.analyze_text(message, system_prompt=self.evaluate_system_prompt)
        if evaluate_result is None:
            raise Exception("Failed to evaluate by AI")

        logger.info(
            f"""***🌟
Location {location_id} evaluated successfully
INPUT:
{input_str}
====
OUTPUT:
{evaluate_result}
"""
        )

        # evaluate summary
        message = f"""
        Please evaluate the summary of the location {location_id} with the following data.)
        Input data:
        {evaluate_result}
        """

        evaluate_summary_result = self.ai_connector.analyze_text(message, system_prompt=self.evaluate_summary_system_prompt, max_tokens=512)
        if evaluate_result is None:
            raise Exception("Failed to evaluate by AI")

        logger.info(evaluate_summary_result)

        # save result
        self.ina_db_connector.upsert_evaluation_result(location_id, input_str, evaluate_result, evaluate_summary_result)

        # notify result
        if target_img_as_bytes is not None:
            Notification.send_discord_message_with_image(
                evaluate_result,
                target_img_as_bytes,
                filename=f"evaluation_{location_id}_{target_date.strftime('%Y%m%d')}.jpg",
            )
        else:
            Notification.send_discord_message(evaluate_result)

        # notify summary as graph
        # sensor info
        sensors = sensor_device_repository().get_by_location(location_id)
        for sensor in sensors:
            if sensor["name"] is None:
                sensor["name"] = sensor["id"]
            sensor["latest"] = sensor_data_repository().get_latest(sensor["id"])
            sensor["latest_aggreated"] = sensor_data_repository().get_latest_aggreated(sensor["id"], limit=72)
            # create graph
            sensor["graph"] = Utils.create_latest_aggregated_graph_as_html(sensor["id"], sensor["latest_aggreated"])


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
    agent.routine()
    agent.ina_db_connector.conn.sync()
