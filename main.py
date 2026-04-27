import json
import os
import threading
import time
import io
import base64

import customtkinter as ctk
from PIL import Image, ImageTk

from ai_client import AIClient
from wechat_handler import WeChatHandler

CONFIG_FILE = "config.json"


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("微信自动回复助手")
        self.geometry("640x740")
        self.resizable(True, False)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.config_data: dict = self._load_config()
        self.running = False
        self.replied_messages: set[str] = set()
        self.ai_client: AIClient | None = None
        self.wechat = WeChatHandler(self.config_data.get("wechat_window_title", "微信"))

        self._preview_open = False
        self._preview_img_ref = None
        self._BASE_W = 640
        self._PREVIEW_W = 380

        self._build_ui()

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def _load_config(self) -> dict:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_config(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config_data, f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        # Outer horizontal container
        self.outer = ctk.CTkFrame(self, fg_color="transparent")
        self.outer.pack(fill="both", expand=True)

        # Left: main panel (fixed width)
        self.main_panel = ctk.CTkFrame(self.outer, fg_color="transparent", width=self._BASE_W)
        self.main_panel.pack(side="left", fill="both", expand=True)
        self.main_panel.pack_propagate(False)

        header = ctk.CTkFrame(self.main_panel, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(15, 0))

        ctk.CTkLabel(header, text="微信自动回复助手",
                     font=("Microsoft YaHei", 20, "bold")).pack(side="left")

        self.preview_btn = ctk.CTkButton(
            header, text="截图预览 ▶", width=110,
            fg_color="#37474f", hover_color="#546e7a",
            command=self._toggle_preview
        )
        self.preview_btn.pack(side="right")

        self.tabs = ctk.CTkTabview(self.main_panel, width=600, height=600)
        self.tabs.pack(padx=20, pady=8, fill="both", expand=True)
        self.tabs.add("主页")
        self.tabs.add("设置")

        self._build_home_tab(self.tabs.tab("主页"))
        self._build_settings_tab(self.tabs.tab("设置"))

        # Right: preview panel (hidden initially)
        self.preview_panel = ctk.CTkFrame(self.outer, width=self._PREVIEW_W, fg_color="#1e1e1e")
        # Not packed yet — shown on demand

        ctk.CTkLabel(self.preview_panel, text="截图预览",
                     font=("Microsoft YaHei", 13, "bold")).pack(pady=(12, 2))
        self.preview_ts_label = ctk.CTkLabel(self.preview_panel, text="等待截图...",
                                              text_color="gray", font=("Consolas", 10))
        self.preview_ts_label.pack()

        scroll = ctk.CTkScrollableFrame(self.preview_panel)
        scroll.pack(fill="both", expand=True, padx=8, pady=8)
        self._preview_label = ctk.CTkLabel(scroll, text="")
        self._preview_label.pack()

    # ---- Preview panel toggle ----

    def _toggle_preview(self):
        if self._preview_open:
            self.preview_panel.pack_forget()
            self.geometry(f"{self._BASE_W}x740")
            self.preview_btn.configure(text="截图预览 ▶")
            self._preview_open = False
        else:
            self.preview_panel.pack(side="left", fill="both", padx=(0, 8), pady=8)
            self.geometry(f"{self._BASE_W + self._PREVIEW_W + 16}x740")
            self.preview_btn.configure(text="截图预览 ◀")
            self._preview_open = True

    def _update_preview(self, screenshot: Image.Image):
        if not self._preview_open:
            return
        max_w = self._PREVIEW_W - 24
        w, h = screenshot.size
        scale = min(max_w / w, 1.0)
        img = screenshot.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        self._preview_img_ref = ImageTk.PhotoImage(img)
        self._preview_label.configure(image=self._preview_img_ref, text="")
        self.preview_ts_label.configure(
            text=f"更新于 {time.strftime('%H:%M:%S')}  ({w}×{h})"
        )

    # ---- Home Tab ----

    def _build_home_tab(self, parent):
        opt_frame = ctk.CTkFrame(parent)
        opt_frame.pack(fill="x", pady=(8, 4))

        ctk.CTkLabel(opt_frame, text="检查间隔 (秒):").grid(row=0, column=0, padx=12, pady=8, sticky="w")
        self.interval_entry = ctk.CTkEntry(opt_frame, width=120)
        self.interval_entry.insert(0, str(self.config_data.get("check_interval", 5)))
        self.interval_entry.grid(row=0, column=1, padx=12, pady=8, sticky="w")

        ctk.CTkLabel(opt_frame, text="微信窗口标题:").grid(row=1, column=0, padx=12, pady=8, sticky="w")
        self.wechat_title_entry = ctk.CTkEntry(opt_frame, width=200)
        self.wechat_title_entry.insert(0, self.config_data.get("wechat_window_title", "微信"))
        self.wechat_title_entry.grid(row=1, column=1, padx=12, pady=8, sticky="w")

        ctk.CTkLabel(parent, text="系统提示词:", anchor="w").pack(fill="x", padx=4, pady=(6, 2))
        self.prompt_box = ctk.CTkTextbox(parent, height=80, font=("Microsoft YaHei", 12))
        self.prompt_box.insert("1.0", self.config_data.get(
            "system_prompt", "你是一个友好的助手，请根据对话内容给出简洁自然的回复，回复要简短自然。"
        ))
        self.prompt_box.pack(fill="x", padx=4)

        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.pack(pady=10)
        ctk.CTkButton(btn_frame, text="保存", width=110,
                      command=self._save_all).pack(side="left", padx=8)
        self.toggle_btn = ctk.CTkButton(
            btn_frame, text="开始监听", width=110,
            fg_color="#2e7d32", hover_color="#1b5e20",
            command=self._toggle
        )
        self.toggle_btn.pack(side="left", padx=8)

        self.status_label = ctk.CTkLabel(parent, text="状态: 未启动",
                                         text_color="gray", font=("Microsoft YaHei", 12))
        self.status_label.pack(pady=(0, 4))

        ctk.CTkLabel(parent, text="运行日志:", anchor="w").pack(fill="x", padx=4)
        self.log_box = ctk.CTkTextbox(parent, font=("Consolas", 11))
        self.log_box.pack(fill="both", expand=True, padx=4, pady=(2, 8))

    # ---- Settings Tab ----

    def _build_settings_tab(self, parent):
        keys_frame = ctk.CTkFrame(parent)
        keys_frame.pack(fill="x", pady=(12, 6), padx=4)

        ctk.CTkLabel(keys_frame, text="API Keys",
                     font=("Microsoft YaHei", 14, "bold")).grid(
            row=0, column=0, columnspan=2, padx=12, pady=(10, 6), sticky="w")

        ctk.CTkLabel(keys_frame, text="Qwen API Key:").grid(row=1, column=0, padx=12, pady=8, sticky="w")
        self.qwen_key_entry = ctk.CTkEntry(keys_frame, width=340, show="*")
        self.qwen_key_entry.insert(0, self.config_data.get("qwen_api_key", ""))
        self.qwen_key_entry.grid(row=1, column=1, padx=12, pady=8)

        ctk.CTkLabel(keys_frame, text="Deepseek API Key:").grid(row=2, column=0, padx=12, pady=8, sticky="w")
        self.deepseek_key_entry = ctk.CTkEntry(keys_frame, width=340, show="*")
        self.deepseek_key_entry.insert(0, self.config_data.get("deepseek_api_key", ""))
        self.deepseek_key_entry.grid(row=2, column=1, padx=12, pady=(8, 12))

        vision_frame = ctk.CTkFrame(parent)
        vision_frame.pack(fill="x", pady=6, padx=4)

        ctk.CTkLabel(vision_frame, text="Vision（图像识别）",
                     font=("Microsoft YaHei", 14, "bold")).grid(
            row=0, column=0, columnspan=2, padx=12, pady=(10, 6), sticky="w")

        ctk.CTkLabel(vision_frame, text="Provider:").grid(row=1, column=0, padx=12, pady=8, sticky="w")
        self.vision_provider = ctk.CTkOptionMenu(
            vision_frame, values=["qwen", "deepseek"], width=160,
            command=self._on_vision_provider_change)
        self.vision_provider.set(self.config_data.get("vision_provider", "qwen"))
        self.vision_provider.grid(row=1, column=1, padx=12, pady=8, sticky="w")

        ctk.CTkLabel(vision_frame, text="模型名:").grid(row=2, column=0, padx=12, pady=8, sticky="w")
        self.vision_model_entry = ctk.CTkEntry(vision_frame, width=260)
        self.vision_model_entry.insert(0, self.config_data.get("vision_model", "qwen-vl-max"))
        self.vision_model_entry.grid(row=2, column=1, padx=12, pady=(8, 12), sticky="w")

        chat_frame = ctk.CTkFrame(parent)
        chat_frame.pack(fill="x", pady=6, padx=4)

        ctk.CTkLabel(chat_frame, text="Chat（生成回复）",
                     font=("Microsoft YaHei", 14, "bold")).grid(
            row=0, column=0, columnspan=2, padx=12, pady=(10, 6), sticky="w")

        ctk.CTkLabel(chat_frame, text="Provider:").grid(row=1, column=0, padx=12, pady=8, sticky="w")
        self.chat_provider = ctk.CTkOptionMenu(
            chat_frame, values=["qwen", "deepseek"], width=160,
            command=self._on_chat_provider_change)
        self.chat_provider.set(self.config_data.get("chat_provider", "qwen"))
        self.chat_provider.grid(row=1, column=1, padx=12, pady=8, sticky="w")

        ctk.CTkLabel(chat_frame, text="模型名:").grid(row=2, column=0, padx=12, pady=8, sticky="w")
        self.chat_model_entry = ctk.CTkEntry(chat_frame, width=260)
        self.chat_model_entry.insert(0, self.config_data.get("chat_model", "qwen-plus"))
        self.chat_model_entry.grid(row=2, column=1, padx=12, pady=(8, 12), sticky="w")

        ctk.CTkButton(parent, text="保存设置", width=140,
                      command=self._save_all).pack(pady=14)

    def _on_vision_provider_change(self, value: str):
        defaults = {"qwen": "qwen-vl-max", "deepseek": "deepseek-vl2"}
        self.vision_model_entry.delete(0, "end")
        self.vision_model_entry.insert(0, defaults.get(value, ""))

    def _on_chat_provider_change(self, value: str):
        defaults = {"qwen": "qwen-plus", "deepseek": "deepseek-chat"}
        self.chat_model_entry.delete(0, "end")
        self.chat_model_entry.insert(0, defaults.get(value, ""))

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _save_all(self):
        try:
            self.config_data["check_interval"] = int(self.interval_entry.get().strip())
        except ValueError:
            pass
        self.config_data["wechat_window_title"] = self.wechat_title_entry.get().strip()
        self.config_data["system_prompt"] = self.prompt_box.get("1.0", "end").strip()
        self.config_data["qwen_api_key"] = self.qwen_key_entry.get().strip()
        self.config_data["deepseek_api_key"] = self.deepseek_key_entry.get().strip()
        self.config_data["vision_provider"] = self.vision_provider.get()
        self.config_data["vision_model"] = self.vision_model_entry.get().strip()
        self.config_data["chat_provider"] = self.chat_provider.get()
        self.config_data["chat_model"] = self.chat_model_entry.get().strip()
        self._save_config()
        self.wechat.window_title = self.config_data.get("wechat_window_title", "微信")
        self._log("配置已保存")

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------

    def _toggle(self):
        if self.running:
            self.running = False
            self.toggle_btn.configure(text="开始监听", fg_color="#2e7d32", hover_color="#1b5e20")
            self.status_label.configure(text="状态: 已停止", text_color="gray")
            return

        self._save_all()

        for role, provider_key in [("Vision", "vision_provider"), ("Chat", "chat_provider")]:
            provider = self.config_data.get(provider_key, "qwen")
            if not self.config_data.get(f"{provider}_api_key", ""):
                self._log(f"错误: {role} 使用 {provider}，但 {provider} API Key 未填写")
                self.tabs.set("设置")
                return

        self.ai_client = AIClient.from_config(self.config_data)
        self.replied_messages = set()
        self.running = True
        self.toggle_btn.configure(text="停止监听", fg_color="#c62828", hover_color="#b71c1c")
        self.status_label.configure(text="状态: 运行中", text_color="#66bb6a")
        threading.Thread(target=self._monitor_loop, daemon=True).start()

    # ------------------------------------------------------------------
    # Monitor loop
    # ------------------------------------------------------------------

    def _monitor_loop(self):
        while self.running:
            try:
                self._check_and_reply()
            except Exception as e:
                self._log(f"[错误] {e}")
            time.sleep(int(self.config_data.get("check_interval", 5)))

    def _check_and_reply(self):
        screenshot = self.wechat.capture_window()
        if screenshot is None:
            self._log("未找到微信窗口，请确认微信已打开")
            return

        self._log("截图成功，正在识别...")
        # Update preview (thread-safe via after)
        self.after(0, self._update_preview, screenshot.copy())

        image_b64 = WeChatHandler.image_to_base64(screenshot)
        result = self.ai_client.analyze_screenshot(image_b64)
        self._log(f"原始识别: {result}")

        history = result.get("history", [])
        needs_reply = result.get("needs_reply", False)
        chat_type = result.get("chat_type", "private")
        at_me = result.get("at_me", False)

        other_msgs = [t for t in history if t.get("sender") == "other"]
        latest_msg = other_msgs[-1].get("text", "").strip() if other_msgs else ""

        self._log(f"识别 [{chat_type}] needs_reply={needs_reply} 消息数={len(history)}: {latest_msg}")

        if chat_type == "group" and not at_me:
            return

        msg_key = f"{latest_msg}|{len(history)}"

        if needs_reply and msg_key not in self.replied_messages:
            self.replied_messages.add(msg_key)
            if len(self.replied_messages) > 200:
                self.replied_messages.pop()
            self._log("生成回复中...")
            reply = self.ai_client.generate_reply(
                history or [{"sender": "other", "text": "你好"}],
                self.config_data.get("system_prompt", "")
            )
            self._log(f"回复: {reply}")
            ok = self.wechat.send_message(reply)
            self._log("回复已发送" if ok else "发送失败，请检查微信窗口")

    # ------------------------------------------------------------------
    # Log (thread-safe)
    # ------------------------------------------------------------------

    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.after(0, self._append_log, f"[{ts}] {msg}\n")

    def _append_log(self, line: str):
        self.log_box.insert("end", line)
        self.log_box.see("end")


if __name__ == "__main__":
    app = App()
    app.mainloop()
