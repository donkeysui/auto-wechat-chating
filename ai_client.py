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


def _normalize_result(d: dict) -> dict:
    """Normalize sender/chat_type fields that models sometimes return verbosely."""
    sender = str(d.get("sender", "")).lower()
    if "other" in sender or "left" in sender or "左" in sender:
        d["sender"] = "other"
    elif "self" in sender or "right" in sender or "右" in sender or "我" in sender:
        d["sender"] = "self"

    chat = str(d.get("chat_type", "")).lower()
    if "group" in chat or "群" in chat:
        d["chat_type"] = "group"
    else:
        d["chat_type"] = "private"

    # needs_reply: accept bool or truthy string
    nr = d.get("needs_reply", False)
    if isinstance(nr, str):
        d["needs_reply"] = nr.lower() in ("true", "yes", "1", "是")

    return d



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
            "分析这张微信聊天截图，严格按以下JSON格式返回，不要输出任何其他内容：\n"
            '{"latest_message":"<最新一条消息的文字>","sender":"other","needs_reply":true,"chat_type":"private","at_me":false}\n'
            "字段规则：\n"
            '- sender: 只能是 "other"（左侧气泡，对方发的）或 "self"（右侧气泡，自己发的）\n'
            '- needs_reply: 布尔值 true 或 false\n'
            '- chat_type: 只能是 "private" 或 "group"\n'
            '- at_me: 群聊中是否@了我，布尔值'
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
        return _normalize_result(_extract_json(response.choices[0].message.content.strip()))

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

