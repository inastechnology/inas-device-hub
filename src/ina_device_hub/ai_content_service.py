import json
from urllib import error, request

from ina_device_hub.general_log import logger
from ina_device_hub.setting import setting


class AIContentService:
    DEFAULT_BASE_URL = "https://api.openai.com/v1"

    def __init__(self):
        self.ai_settings = setting().get("ai")
        self.instagram_settings = setting().get("instagram")

    def generate_instagram_caption(self, media_context: dict):
        visual_summary = self._summarize_visuals(media_context)
        if not self.ai_settings.get("text_analyze_api_key"):
            return visual_summary

        sensor_snapshot = json.dumps(
            media_context.get("sensor_snapshot", {}),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        serialized_context = json.dumps(
            media_context,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        prompt = (
            "以下の観察情報をもとに、日本語の Instagram 投稿文を作成してください。"
            "2-4文で、最後に 3-8 個のハッシュタグを付けてください。"
            "過剰な断定は避け、観察ベースで自然な表現にしてください。\n\n"
            f"観察サマリー:\n{visual_summary}\n\n"
            f"センサースナップショット:\n{sensor_snapshot}\n\n"
            "補足情報:\n"
            f"{serialized_context}"
        )
        messages = [
            {
                "role": "system",
                "content": "あなたは植物観察用の Instagram 編集者です。簡潔で具体的に書いてください。",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]
        return self._chat_completion(
            api_key=self.ai_settings.get("text_analyze_api_key"),
            base_url=self.ai_settings.get("text_analyze_base_url"),
            model=self.ai_settings.get("text_analyze_model"),
            messages=messages,
            temperature=0.8,
        )

    def _summarize_visuals(self, media_context: dict):
        if not self.ai_settings.get("image_analyze_api_key"):
            return self._fallback_visual_summary(media_context)

        plant_position_prompt = (
            self.instagram_settings.get("plant_position_prompt") or "なし"
        )
        content = [
            {
                "type": "text",
                "text": (
                    "次の植物観察メディアを見て、Instagram 投稿用の観察メモを日本語で 3-5 文に要約してください。"
                    "タイムラプス動画 URL があれば、その変化も考慮してください。"
                    " 植物配置メモ: "
                    f"{plant_position_prompt}"
                ),
            }
        ]
        for image_url in media_context.get("image_urls", [])[:3]:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": image_url},
                }
            )
        if media_context.get("video_url"):
            content.append(
                {
                    "type": "text",
                    "text": f"タイムラプス動画 URL: {media_context['video_url']}",
                }
            )
        messages = [
            {
                "role": "system",
                "content": "あなたは植物観察の要点を整理するアシスタントです。",
            },
            {
                "role": "user",
                "content": content,
            },
        ]
        try:
            return self._chat_completion(
                api_key=self.ai_settings.get("image_analyze_api_key"),
                base_url=self.ai_settings.get("image_analyze_base_url"),
                model=self.ai_settings.get("image_analyze_model"),
                messages=messages,
                temperature=0.3,
            )
        except RuntimeError:
            logger.exception("Falling back to non-vision summary")
            return self._fallback_visual_summary(media_context)

    def _fallback_visual_summary(self, media_context: dict):
        return (
            f"{media_context.get('frame_count', 0)} 枚の定点画像からタイムラプスを作成しました。"
            " 撮影期間は "
            f"{media_context.get('start_at')} から "
            f"{media_context.get('end_at')} です。"
            " 植物配置メモ: "
            f"{self.instagram_settings.get('plant_position_prompt') or 'なし'}"
        )

    def _chat_completion(
        self,
        api_key: str,
        base_url: str,
        model: str,
        messages: list,
        temperature: float,
    ):
        if not api_key or not model:
            raise RuntimeError("AI settings are incomplete")

        url = f"{(base_url or self.DEFAULT_BASE_URL).rstrip('/')}" "/chat/completions"
        payload = json.dumps(
            {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }
        ).encode("utf-8")
        req = request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=90) as response:
                body = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(detail) from exc

        return self._extract_text(body).strip()

    def _extract_text(self, response_body: dict):
        choices = response_body.get("choices", [])
        if not choices:
            return ""

        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(
                item.get("text", "") for item in content if item.get("type") == "text"
            )
        return ""


__instance = None


def ai_content_service():
    global __instance
    if not __instance:
        __instance = AIContentService()
    return __instance
