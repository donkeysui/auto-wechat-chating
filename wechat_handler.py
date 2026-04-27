import base64
import io
import time

import pyautogui
import pyperclip
import win32gui
import win32con
import win32api
from PIL import Image


def _find_input_via_uia(hwnd: int):
    """
    Try to locate the WeChat text-input control using UI Automation.
    Returns (center_x, center_y) or None if unavailable.
    """
    try:
        import comtypes.client
        import comtypes.gen.UIAutomationClient as UIA

        uia = comtypes.client.CreateObject(
            "{ff48dba4-60ef-4201-aa87-54103eef594e}",
            interface=UIA.IUIAutomation
        )
        element = uia.ElementFromHandle(hwnd)
        # Search for Edit controls (ControlType 50004)
        condition = uia.CreatePropertyCondition(
            UIA.UIA_ControlTypePropertyId, UIA.UIA_EditControlTypeId
        )
        found = element.FindAll(UIA.TreeScope_Descendants, condition)
        if found and found.Length > 0:
            # Pick the last Edit element (usually the message input box)
            el = found.GetElement(found.Length - 1)
            rect = el.CurrentBoundingRectangle
            cx = (rect.left + rect.right) // 2
            cy = (rect.top + rect.bottom) // 2
            return cx, cy
    except Exception:
        pass
    return None


class WeChatHandler:
    def __init__(self, window_title: str = "微信"):
        self.window_title = window_title
        self.hwnd = None

    # ------------------------------------------------------------------
    # Window discovery
    # ------------------------------------------------------------------

    def find_window(self) -> bool:
        """Find the WeChat main window by title substring."""
        found = []

        def _cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if self.window_title in title:
                    found.append(hwnd)

        win32gui.EnumWindows(_cb, None)
        if found:
            self.hwnd = found[0]
            return True
        self.hwnd = None
        return False

    # ------------------------------------------------------------------
    # Screenshot
    # ------------------------------------------------------------------

    def capture_window(self) -> Image.Image | None:
        """Capture the WeChat window and return a PIL Image, or None on failure."""
        if not self.hwnd and not self.find_window():
            return None
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

    # ------------------------------------------------------------------
    # Send message
    # ------------------------------------------------------------------

    def _get_input_position(self) -> tuple[int, int]:
        """
        Return (x, y) of the message input box.
        Tries UI Automation first; falls back to bottom-centre estimate.
        """
        pos = _find_input_via_uia(self.hwnd)
        if pos:
            return pos
        # Fallback: estimate bottom-centre of window
        rect = win32gui.GetWindowRect(self.hwnd)
        x, y, w, h = rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1]
        return x + w // 2, y + h - 80

    def send_message(self, text: str) -> bool:
        """
        Paste text into the WeChat input box and press Enter.
        Uses clipboard so Chinese characters are handled correctly.
        """
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
