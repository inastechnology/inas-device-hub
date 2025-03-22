import base64

from openai import OpenAI

from ina_device_hub.general_log import logger
from ina_device_hub.setting import setting


class AIConnector:
    def __init__(self):
        self.ai_setting = setting().get("ai")

    def analyze_image(self, target_image: bytes, file_format: str = "jpg", system_prompt: str = None, message: str = None, max_tokens: int = 2048) -> str:
        image_analyze_setting = self.ai_setting["image_analyze"]
        api_key = image_analyze_setting["api_key"]
        base_url = image_analyze_setting.get("base_url")
        model = image_analyze_setting["model"]
        client = OpenAI(api_key=api_key, base_url=base_url)

        if system_prompt is None:
            system_prompt = """
            Please write a detailed analysis of the image.
            """

        content = []
        if message:
            content.append({"type": "text", "text": message})
        target_image_base64 = base64.b64encode(target_image).decode("utf-8")
        content.append({"type": "image_url", "image_url": {"url": f"data:image/{file_format};base64,{target_image_base64}"}})

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
                {"role": "user", "content": content},
            ],
            temperature=0,
            max_tokens=max_tokens,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0,
            response_format={"type": "text"},
        )

        return response.choices[0].message.content

    def analyze_text(self, message: str, system_prompt: str = None, max_tokens: int = 2048) -> str:
        text_analyze_setting = self.ai_setting["text_analyze"]
        api_key = text_analyze_setting["api_key"]
        base_url = text_analyze_setting.get("base_url")
        model = text_analyze_setting["model"]
        client = OpenAI(api_key=api_key, base_url=base_url)

        messages = []
        if system_prompt is not None:
            messages.append({"role": "system", "content": [{"type": "text", "text": system_prompt}]})
        messages.append({"role": "user", "content": [{"type": "text", "text": message}]})

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0,
            max_tokens=max_tokens,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0,
            response_format={"type": "text"},
            stream=False if "seek" in model.lower() else True,
        )

        return response.choices[0].message.content


__instance = None


def ai_connector():
    global __instance
    if not __instance:
        __instance = AIConnector()
    return __instance
