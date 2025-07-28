from io import BytesIO
import os
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
import json

from ina_device_hub.instagram_poster import instagram_poster
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
from PIL import Image


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
    Based solely on the provided information, please perform a brief evaluation of the plant. Adhere strictly to the details given, avoid assumptions, and respond with "unknown" if certain data is unavailable. It is critical to avoid any fabrication or hallucination of information.

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
        self.instagram_poster = instagram_poster()
        self.past_post_summary = {}
        self.past_post_summary_file = os.path.join(self.setting.get_work_dir(), "past_post_summary.json")
        self._load_past_post_summary()

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
        yesterday = datetime.now(UTC) - timedelta(days=1)
        # get all locations
        location_dict = self.location_repository.get_all()
        try:
            if location_dict is None or len(location_dict) == 0:
                raise Exception("No locations found")

            for key, location in location_dict.items():
                location_id = key
                self.evaluate(location_id, yesterday)
        except Exception as e:
            logger.exception(f"[INA AGENT]Routine failed: {e}")
        finally:
            logger.info("[INA AGENT]Routine finished")

        try:
            self.post_sns(yesterday)
        except Exception as e:
            logger.exception(f"[INA AGENT]Failed to post SNS: {e}")

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
        image_tuples = []
        if target_img_as_bytes is not None:
            image_tuples.append((f"evaluation_{location_id}_{target_date.strftime('%Y%m%d')}.jpg", target_img_as_bytes))

        # notify summary as graph
        # sensor info
        sensors = sensor_device_repository().get_by_location(location_id)
        for sensor in sensors:
            if sensor["name"] is None:
                sensor["name"] = sensor["id"]
            sensor["latest"] = sensor_data_repository().get_latest(sensor["id"])
            sensor["latest_aggreated"] = sensor_data_repository().get_latest_aggreated(sensor["id"], limit=72)
            # create graph as image
            img = Utils.create_latest_aggregated_graph_as_image(sensor["id"], sensor["latest_aggreated"], image_format="webp")
            if img is not None:
                image_tuples.append((f"sensor_{sensor['id']}_latest_aggregated.webp", img))

        if len(image_tuples) > 0:
            # send image to discord
            Notification.send_discord_message_with_image(
                evaluate_result,
                image_tuples,
            )
        else:
            Notification.send_discord_message(evaluate_result)

    def post_sns(self, target_date: datetime):
        # post to instagram
        yyyymmdd = target_date.strftime("%Y%m%d")

        post_info: dict = self.setting.get("instagram")["post_info"]
        # ===================================================
        # 1. センサー値の取得と整形
        # ===================================================
        # センサー値の取得
        sensor_id = post_info["sensor_id"]
        camera_id = post_info["camera_id"]
        __input_data = {"Analyze Date": yyyymmdd, "sensor_data": {}, "image": None, "previous_post_summary": []}

        # 直近のセンサー値
        sensor_data = sensor_data_repository().get_latest_aggreated(sensor_id, limit=12)
        logger.info(f"Fetched sensor data for {len(sensor_data)} records on {yyyymmdd}")
        if not sensor_data:
            logger.warning(f"No sensor data found for {sensor_id} on {yyyymmdd}")
            return

        # 直近のセンサー値をグラフ化
        graph_img_bytes = Utils.create_latest_aggregated_graph_as_image(sensor_id, sensor_data, image_format="jpg")

        # filter invalid data
        input_sensor_data = []
        for elem in sensor_data:
            try:
                extra = elem.get("extra", {})
                if "light_status" in extra and extra["light_status"] is not None:
                    del extra["light_status"]  # Remove light status from extra

            except Exception as e:
                extra = {}
            data_as_dict = {}
            if elem.get("temp") is not None and elem.get("temp") > -1000:
                data_as_dict["temp"] = elem.get("temp")
            if elem.get("tds") is not None and elem.get("tds") > -1000:
                data_as_dict["tds"] = elem.get("tds")
            if elem.get("ec") is not None and elem.get("ec") > -1000:
                data_as_dict["ec"] = elem.get("ec")
            if elem.get("ph") is not None and elem.get("ph") > -1000:
                data_as_dict["ph"] = elem.get("ph")
            if elem.get("dissolved_oxygen") is not None and elem.get("dissolved_oxygen") > -1000:
                data_as_dict["dissolved_oxygen"] = elem.get("dissolved_oxygen")
            if elem.get("ammonia") is not None and elem.get("ammonia") > -1000:
                data_as_dict["ammonia"] = elem.get("ammonia")
            if elem.get("nitrate") is not None and elem.get("nitrate") > -1000:
                data_as_dict["nitrate"] = elem.get("nitrate")
            if elem.get("created_at"):
                data_as_dict["created_at"] = elem.get("created_at").strftime("%Y-%m-%d %H:%M:%S")
            if extra:
                data_as_dict["extra"] = extra
            input_sensor_data.append(data_as_dict)
        __input_data["sensor_data"][sensor_id] = input_sensor_data

        # ==================================================
        # 2. 画像の取得と分析
        # ==================================================
        # 直近7日分の中央の画像を取得
        # ==================================================
        _past_plant_images = []
        _target_date = target_date
        max_image_len = 6 * 24
        for i in range(7):
            # get image
            date_filter = _target_date.strftime("%Y%m%d")
            image_pathes = camera_image_repository().get_date_image_by_id(camera_id, date_filter, limit=2 * max_image_len)

            # 中央の画像を選択
            target_img = None
            if image_pathes:
                middle_index = len(image_pathes) // 2
                target_img = image_pathes[middle_index]
                logger.info(f"Target image found: {target_img}")
                # download image as bytes
                target_img_as_bytes = camera_image_repository().download_image(target_img["key"])
                if target_img_as_bytes:
                    _past_plant_images.append(target_img_as_bytes)
            else:
                logger.info("No target image found")
                target_img_as_bytes = None
            _target_date -= timedelta(days=1)

        # 画像の説明をAIに依頼
        system_prompt = """
        You are an agricultural specialist AI.
        Your task is to analyze the plant image and extract observable features.
        Furthermore, you can analyze changes in the condition of plants from images provided each day.
        Please describe the plant's condition based on the image.
        """
        # plant_position_prompt = "From left: blueberry, lychee"
        plant_position_prompt = post_info["plant_position_prompt"]
        plant_status = self.ai_connector.analyze_multi_images(
            _past_plant_images,
            system_prompt=system_prompt,
            message=f"Those are the images of the plant({plant_position_prompt}) taken in the last {len(_past_plant_images)} days ordered by newer to older.",
            max_tokens=512,
        )

        logger.info(f"Plant status description: {plant_status}")

        __input_data["image"] = plant_status

        # ==================================================
        # 3. 前回の投稿の要約を取得
        # ==================================================
        previous_post_summary = self.past_post_summary[sensor_id] if sensor_id in self.past_post_summary else None
        if previous_post_summary and isinstance(previous_post_summary, list) and len(previous_post_summary) > 0:
            # 前回の投稿の要約が存在する場合は、最新の要約
            __input_data["previous_post_summary"] = previous_post_summary[-1::1]  # Get the last summary
            logger.info(f"Previous post summary found for sensor {sensor_id}: {__input_data['previous_post_summary']}")
        else:
            # 前回の投稿の要約が存在しない場合は、空のリスト
            logger.info(f"No previous post summary found for sensor {sensor_id}, initializing empty list.")
            __input_data["previous_post_summary"] = []

        # ==================================================
        # 日曜日の場合は is_weekly_highlight_day = True
        __input_data["is_weekly_highlight_day"] = target_date.weekday() == 5  # 5 is Saturday

        # ==================================================
        # 4. AIによる投稿内容の生成
        # ==================================================
        input_str = json.dumps(__input_data, ensure_ascii=False)
        logger.info(f"Input data for AI: {input_str}")
        system_prompt = """
You are AgriGrow AI, a poetic and observant virtual assistant who specializes in horticulture. Your task is to craft graceful, emotionally resonant Instagram captions for daily plant-growth timelapse videos.

Guidelines:

1. Write in the specified language with a lyrical, expressive tone—evoking the quiet beauty of everyday growth.
2. Offer a subtle daily observation based solely on the supplied sensor data and image analysis—note gentle shifts in color, form, or rhythm.
3. **Creative Essence (choose exactly ONE per post):**
   a. A short original poetic line (haiku-like 5-7-5 or tanka-like 5-7-5-7-7).
   b. A playful or poetic metaphor / analogy.
   c. A soft personification, hinting at what the plant might “feel.”
   d. (Only on the designated weekly-highlight day) a concise summary of the week’s most notable change.
   *Do not combine multiple options in the same caption.*
4. Vary phrasing and mood day-to-day so returning followers always find something fresh.
5. Include up to three thoughtful hashtags that match the post’s theme.
6. Emojis are optional; if used, keep them minimal and harmonious.
7. Output plain text only—no markdown, HTML, personal details, or location data.
8. Conclude with:
   “– generated by an AI assistant 🌱”
9. If a grower-submitted photo is present, acknowledge it gracefully (e.g., “Through the eyes of our grower…”).
"""

        message = f"""
        Please generate a post for Instagram with the following data.(please output language:{self.setting.get("language")})
        Input data:
        {input_str}
        """
        post_content = self.ai_connector.analyze_text(message, system_prompt=system_prompt)
        if post_content is None:
            raise Exception("Failed to generate post content by AI")
        logger.info(f"Generated post content: {post_content}")
        # save the post content to past_post_summary
        self._append_past_post_summary(sensor_id, post_content)

        # ==================================================
        # 5. 投稿する動画の生成
        # ==================================================
        # camera_id に対応する画像を取得
        # ===================================================
        image_bytes_list, video_width, video_height = self._fetch_image_list(camera_id, target_date)
        if not image_bytes_list:
            logger.warning(f"No images found for camera {camera_id} on {target_date.strftime('%Y-%m-%d')}")
            image_bytes_list = []

        mp4_bytes = Utils.jpeg_iterable_to_mp4_bytes(
            image_bytes_list,
            width=video_width,
            height=video_height,
            fps=24,  # 24 FPS ()
        )

        # ===================================================
        # 6. カバー画像の生成
        # ===================================================
        # 最新の画像を取得
        latest_image = image_bytes_list[-1] if image_bytes_list else None
        # 画像にキャプションを追加
        cover_image_bytes = None
        if latest_image:
            cropped_image_bytes = Utils.crop_image(latest_image, 4 / 5)[0]
            # 日付を追加してカバー画像を生成
            cover_text = datetime.now(UTC).strftime("%Y-%m-%d") + " 生育記録"
            cover_image_bytes = Utils.add_text_overlay(cropped_image_bytes, cover_text)
        else:
            logger.error("Failed to generate cover image: No latest image found.")

        self.instagram_poster.post_growth_record([graph_img_bytes], caption=post_content, mp4_bytes=mp4_bytes, cover_image_bytes=cover_image_bytes)

        if len(cover_image_bytes) > 0:
            # send image to discord
            Notification.send_discord_message_with_image(
                f"posted to Instagram on {target_date.strftime('%Y-%m-%d')}:\n{post_content}",
                [(f"posted_to_instagram_{target_date.strftime('%Y%m%d')}.jpg", cover_image_bytes)],
            )
        else:
            Notification.send_discord_message(f"posted to Instagram on {target_date.strftime('%Y-%m-%d')}:\n{post_content}")

    def _load_past_post_summary(self):
        if os.path.exists(self.past_post_summary_file):
            try:
                with open(self.past_post_summary_file) as f:
                    self.past_post_summary = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load past post summary: {e}")
                self.past_post_summary = {}
        else:
            self.past_post_summary = {}

    def _append_past_post_summary(self, sensor_id: str, summary: str):
        MAX_SUMMARY_LENGTH = 10  # noqa: N806
        # 先頭に日付を追加
        summary = f"{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}\n{summary}"
        if sensor_id not in self.past_post_summary:
            self.past_post_summary[sensor_id] = []
        self.past_post_summary[sensor_id].append(summary)
        # Limit the number of summaries to MAX_SUMMARY_LENGTH
        if len(self.past_post_summary[sensor_id]) > MAX_SUMMARY_LENGTH:
            self.past_post_summary[sensor_id] = self.past_post_summary[sensor_id][-MAX_SUMMARY_LENGTH:]
        # Save the past post summary to file
        with open(self.past_post_summary_file, "w") as f:
            json.dump(self.past_post_summary, f, indent=4, ensure_ascii=False)

    def _fetch_image_list(self, camera_id: str, target_date: datetime) -> list[bytes]:
        video_width = 0
        video_height = 0

        def forming_image(image_bytes: bytes) -> bytes:
            nonlocal video_width, video_height
            # 画像をPILで開く
            # 画像を4:5にクロップして、サイズを半分にする
            cropped_bytes, cropped_width, cropped_height = Utils.crop_image(image_bytes, 4 / 5)
            cropped_image = Image.open(BytesIO(cropped_bytes))
            resized_image = cropped_image.resize((cropped_width // 2, cropped_height // 2))
            video_width, video_height = resized_image.size
            resized_bytes = BytesIO()
            resized_image.save(resized_bytes, format="JPEG", quality=95)
            return resized_bytes.getvalue()

        max_image_len = 6 * 24
        camera_latest_images = []
        date_filter = target_date.strftime("%Y%m%d")
        today_images = camera_image_repository().get_date_image_by_id(camera_id, date_filter, limit=max_image_len)
        logger.info(f"Fetched {len(today_images)} images for camera {camera_id} on {date_filter}")

        camera_latest_images = today_images

        if len(today_images) < max_image_len:
            # 昨日の画像を取得
            date_filter = (target_date - timedelta(days=1)).strftime("%Y%m%d")
            yesterday_images = camera_image_repository().get_date_image_by_id(camera_id, date_filter, limit=2 * max_image_len)
            logger.info(f"Fetched {len(yesterday_images)} images for camera {camera_id} on {date_filter}")
            # 昨日の画像を追加
            camera_latest_images.extend(yesterday_images)
            # sort as key
            camera_latest_images.sort(key=lambda x: x.get("key"))
            if len(camera_latest_images) > max_image_len:
                camera_latest_images = camera_latest_images[len(camera_latest_images) - max_image_len :]
        return [forming_image(camera_image_repository().download_image(img["key"])) for img in camera_latest_images], video_width, video_height


__instance = None


def ina_agent():
    global __instance
    if not __instance:
        __instance = InaAgent()

    return __instance


if __name__ == "__main__":
    setting().settings["turso"]["local_db_path"] = os.path.join(os.path.expanduser(setting().get_work_dir()), ".test.db")
    agent = InaAgent()
    # agent.routine()
    agent.ina_db_connector.conn.sync()

    test_count = 10
    for i in range(test_count):
        try:
            contents = agent.post_sns(datetime.now(UTC) - timedelta(days=1))
            Notification.send_discord_message(contents)
        except Exception as e:
            logger.exception(f"[INA AGENT]Failed to post SNS: {e}")
