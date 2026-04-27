import base64
import io
import time

import pyautogui
import pyperclip
import win32gui
import win32con
import win32api
from PIL import Image


def _capture_via_wgc(window_title: str) -> Image.Image | None:
    """
    Capture a window using Windows Graphics Capture API (supports GPU-accelerated apps).
    Returns a PIL Image or None if unavailable.
    """
    try:
        import numpy as np
        from windows_capture import WindowsCapture, InternalCaptureControl

        result: list[Image.Image] = []

        capture = WindowsCapture(
            cursor_capture=False,
            draw_border=False,
            monitor_index=None,
            window_name=window_title,
        )

        @capture.event
        def on_frame_arrived(frame, capture_control: InternalCaptureControl):
            arr = frame.to_numpy(copy=True)   # shape: (H, W, 4) BGRA
            img = Image.fromarray(arr[:, :, [2, 1, 0, 3]], "RGBA").convert("RGB")
            result.append(img)
            capture_control.stop()

        @capture.event
        def on_closed():
            pass

        capture.start()  # blocks until stop() is called

        return result[0] if result else None
    except Exception:
        return None


def _find_input_via_uia(hwnd: int):
    try:
        import comtypes.client
        import comtypes.gen.UIAutomationClient as UIA

        uia = comtypes.client.CreateObject(
            "{ff48dba4-60ef-4201-aa87-54103eef594e}",
            interface=UIA.IUIAutomation
        )
        element = uia.ElementFromHandle(hwnd)
        condition = uia.CreatePropertyCondition(
            UIA.UIA_ControlTypePropertyId, UIA.UIA_EditControlTypeId
        )
        found = element.FindAll(UIA.TreeScope_Descendants, condition)
        if found and found.Length > 0:
            el = found.GetElement(found.Length - 1)
            rect = el.CurrentBoundingRectangle
            return (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2
    except Exception:
        pass
    return None


class WeChatHandler:
    def __init__(self, window_title: str = "微信"):
        self.window_title = window_title
        self.hwnd = None

    def find_window(self) -> bool:
        found = []

        def _cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                if self.window_title in win32gui.GetWindowText(hwnd):
                    found.append(hwnd)

        win32gui.EnumWindows(_cb, None)
        if found:
            self.hwnd = found[0]
            return True
        self.hwnd = None
        return False

    def capture_window(self) -> Image.Image | None:
        if not self.hwnd and not self.find_window():
            return None

        # WGC captures directly by window name — no need to bring to foreground
        img = _capture_via_wgc(self.window_title)
        if img is not None:
            return img

        # Fallback: pyautogui GDI capture (requires window to be visible)
        try:
            rect = win32gui.GetWindowRect(self.hwnd)
            x, y, w, h = rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1]
            if w <= 0 or h <= 0:
                return None
            win32gui.SetForegroundWindow(self.hwnd)
            time.sleep(0.3)
            return pyautogui.screenshot(region=(x, y, w, h))
        except Exception:
            self.hwnd = None
            return None

    @staticmethod
    def image_to_base64(image: Image.Image) -> str:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()

    def _get_input_position(self) -> tuple[int, int]:
        pos = _find_input_via_uia(self.hwnd)
        if pos:
            return pos
        rect = win32gui.GetWindowRect(self.hwnd)
        x, y, w, h = rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1]
        return x + w // 2, y + h - 80

    def send_message(self, text: str) -> bool:
        if not self.hwnd and not self.find_window():
            return False
        try:
            win32gui.SetForegroundWindow(self.hwnd)
            time.sleep(0.3)
            ix, iy = self._get_input_position()
            pyautogui.click(ix, iy)
            time.sleep(0.2)
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.15)
            pyautogui.press("enter")
            return True
        except Exception:
            return False

