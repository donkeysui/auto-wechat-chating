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
    # Normalize chat_type
    chat = str(d.get("chat_type", "")).lower()
    d["chat_type"] = "group" if ("group" in chat or "群" in chat) else "private"

    # Normalize needs_reply
    nr = d.get("needs_reply", False)
    if isinstance(nr, str):
        d["needs_reply"] = nr.lower() in ("true", "yes", "1", "是")

    # Normalize at_me
    am = d.get("at_me", False)
    if isinstance(am, str):
        d["at_me"] = am.lower() in ("true", "yes", "1", "是")

    # Normalize history entries
    history = d.get("history", [])
    for turn in history:
        s = str(turn.get("sender", "")).lower()
        if "other" in s or "left" in s or "左" in s:
            turn["sender"] = "other"
        else:
            turn["sender"] = "self"

    return d


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
        """
        Extract full conversation history from screenshot and determine reply intent.
        Returns: {
          "history": [{"sender": "other"|"self", "text": "..."}],
          "needs_reply": bool,
          "chat_type": "private"|"group",
          "at_me": bool
        }
        """
        prompt = (
            "仔细阅读这张微信聊天截图，提取聊天记录并以JSON格式返回，不要输出任何其他内容：\n"
            '{"history":[{"sender":"other","text":"消息内容"},{"sender":"self","text":"消息内容"}],'
            '"needs_reply":true,"chat_type":"private","at_me":false}\n'
            "规则：\n"
            "- history: 按时间顺序列出截图中所有可见消息，左侧气泡 sender=other，右侧气泡 sender=self\n"
            '- needs_reply: 最新一条是 other 发的且需要回复则为 true\n'
            '- chat_type: "private" 或 "group"\n'
            "- at_me: 群聊中最新消息是否@了我"
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
                max_tokens=800
            )

        response = _call_with_retry(_do_call)
        return _normalize_result(_extract_json(response.choices[0].message.content.strip()))

    def generate_reply(self, history: list[dict], system_prompt: str) -> str:
        """Generate a reply given full conversation history."""
        # Build messages from history
        messages = [{"role": "system", "content": system_prompt}]
        for turn in history:
            role = "user" if turn.get("sender") == "other" else "assistant"
            text = turn.get("text", "").strip()
            if text:
                messages.append({"role": role, "content": text})

        # Ensure last message is from user side
        if not messages or messages[-1]["role"] != "user":
            messages.append({"role": "user", "content": "请回复"})

        def _do_call():
            return self.chat_client.chat.completions.create(
                model=self.chat_model,
                messages=messages,
                max_tokens=300
            )

        response = _call_with_retry(_do_call)
        return response.choices[0].message.content.strip()

