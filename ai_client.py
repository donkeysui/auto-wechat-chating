import json
import re
import time
from openai import OpenAI

_RETRY_DELAYS = [1, 3, 7]

_BASE_URLS = {
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "deepseek": "https://api.deepseek.com",
}


def _call_with_retry(fn, *args, **kwargs):
    last_exc = None
    for delay in [0] + _RETRY_DELAYS:
        if delay:
            time.sleep(delay)
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
    raise last_exc


def _extract_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*?\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return {"latest_message": "", "sender": "unknown", "needs_reply": False,
            "chat_type": "private", "at_me": False}


class AIClient:
    def __init__(self, vision_client: OpenAI, vision_model: str,
                 chat_client: OpenAI, chat_model: str):
        self.vision_client = vision_client
        self.vision_model = vision_model
        self.chat_client = chat_client
        self.chat_model = chat_model

    @classmethod
    def from_config(cls, config: dict) -> "AIClient":
        """Build an AIClient from the app config dict."""
        def _make_client(provider: str) -> OpenAI:
            key_field = f"{provider}_api_key"
            api_key = config.get(key_field, "")
            base_url = _BASE_URLS.get(provider, _BASE_URLS["qwen"])
            return OpenAI(api_key=api_key, base_url=base_url)

        vision_provider = config.get("vision_provider", "qwen")
        chat_provider = config.get("chat_provider", "qwen")

        return cls(
            vision_client=_make_client(vision_provider),
            vision_model=config.get("vision_model", "qwen-vl-max"),
            chat_client=_make_client(chat_provider),
            chat_model=config.get("chat_model", "qwen-plus"),
        )

    def analyze_screenshot(self, image_base64: str) -> dict:
        prompt = (
            "这是一张微信聊天截图。请分析并严格以JSON格式返回以下字段，不要输出任何其他内容：\n"
            "{\n"
            '  "latest_message": "最新一条消息的完整文字内容",\n'
            '  "sender": "self（右侧气泡）或 other（左侧气泡）",\n'
            '  "needs_reply": true或false,\n'
            '  "chat_type": "private（私聊）或 group（群聊）",\n'
            '  "at_me": true或false（群聊中消息是否包含@我）\n'
            "}"
        )

        def _do_call():
            return self.vision_client.chat.completions.create(
                model=self.vision_model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
                        {"type": "text", "text": prompt}
                    ]
                }],
                max_tokens=400
            )

        response = _call_with_retry(_do_call)
        return _extract_json(response.choices[0].message.content.strip())

    def generate_reply(self, message: str, system_prompt: str) -> str:
        def _do_call():
            return self.chat_client.chat.completions.create(
                model=self.chat_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message}
                ],
                max_tokens=300
            )

        response = _call_with_retry(_do_call)
        return response.choices[0].message.content.strip()

