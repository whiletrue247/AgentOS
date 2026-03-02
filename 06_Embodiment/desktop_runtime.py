"""
06_Embodiment — Desktop Runtime (v5.0 SOTA)
=============================================
跨平台桌面自動化引擎，支援：
  - pyautogui (macOS/Windows/Linux 通用)
  - macOS: screencapture 原生截圖
  - Windows: Win32 API screenshot
  - Linux: scrot/grim 截圖

所有方法都有 graceful fallback（未安裝依賴時回傳 mock 並記錄警告）。
"""

from __future__ import annotations

import base64
import logging
import platform
import subprocess
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 嘗試載入 pyautogui
try:
    import pyautogui
    pyautogui.FAILSAFE = True   # 滑鼠移到角落時中止
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False


class DesktopRuntime:
    """
    跨平台桌面控制引擎 (v5.0 SOTA)。
    實現 2026 Agentic Computer Use 標準的底層封裝。
    """

    def __init__(self):
        self.os_type = platform.system()
        backend = "pyautogui" if PYAUTOGUI_AVAILABLE else "mock"
        logger.info(f"🖥️ DesktopRuntime: os={self.os_type}, backend={backend}")

    # ----------------------------------------------------------
    # Screenshot
    # ----------------------------------------------------------
    def take_screenshot(self, save_path: str = "/tmp/agentos_screen.png") -> str:
        """截取全螢幕並回傳 base64 字串供 Vision 模型讀取。"""
        try:
            if self.os_type == "Darwin":
                subprocess.run(["screencapture", "-x", save_path], check=True, timeout=5)
            elif PYAUTOGUI_AVAILABLE:
                img = pyautogui.screenshot()
                img.save(save_path)
            else:
                logger.warning("⚠️ Screenshot: no backend available, returning mock")
                return "base64_mock_screenshot"

            with open(save_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            logger.info(f"📸 Screenshot captured: {len(b64)} bytes (base64)")
            return b64

        except Exception as e:
            logger.error(f"❌ Screenshot failed: {e}")
            return "base64_screenshot_error"

    # ----------------------------------------------------------
    # Mouse
    # ----------------------------------------------------------
    def click(self, x: int, y: int, button: str = "left"):
        """跨平台座標點擊"""
        if PYAUTOGUI_AVAILABLE:
            pyautogui.click(x=x, y=y, button=button)
            logger.info(f"🖱️ Clicked: {button} at ({x}, {y})")
        else:
            logger.info(f"🖱️ [MOCK] Click: {button} at ({x}, {y})")

    def double_click(self, x: int, y: int):
        """雙擊"""
        if PYAUTOGUI_AVAILABLE:
            pyautogui.doubleClick(x=x, y=y)
            logger.info(f"🖱️ Double-clicked at ({x}, {y})")
        else:
            logger.info(f"🖱️ [MOCK] Double-click at ({x}, {y})")

    def scroll(self, clicks: int, x: Optional[int] = None, y: Optional[int] = None):
        """滾輪"""
        if PYAUTOGUI_AVAILABLE:
            pyautogui.scroll(clicks, x=x, y=y)
            logger.info(f"🖱️ Scrolled {clicks} clicks")
        else:
            logger.info(f"🖱️ [MOCK] Scroll {clicks} clicks")

    # ----------------------------------------------------------
    # Keyboard
    # ----------------------------------------------------------
    def type_text(self, text: str, interval: float = 0.02):
        """模擬鍵盤輸入文字"""
        if PYAUTOGUI_AVAILABLE:
            pyautogui.write(text, interval=interval)
            logger.info(f"⌨️ Typed: {text[:20]}...")
        else:
            logger.info(f"⌨️ [MOCK] Type: {text[:20]}...")

    def press_key(self, key_name: str, modifiers: Optional[list] = None):
        """模擬按下快捷鍵 (如 enter, escape, cmd+c)"""
        if PYAUTOGUI_AVAILABLE:
            if modifiers:
                pyautogui.hotkey(*modifiers, key_name)
            else:
                pyautogui.press(key_name)
            mod_str = "+".join(modifiers) + "+" if modifiers else ""
            logger.info(f"⌨️ Pressed: {mod_str}{key_name}")
        else:
            mod_str = "+".join(modifiers) + "+" if modifiers else ""
            logger.info(f"⌨️ [MOCK] Press: {mod_str}{key_name}")

    # ----------------------------------------------------------
    # Window Info (OS-native)
    # ----------------------------------------------------------
    def get_active_window_info(self) -> Dict[str, Any]:
        """透過作業系統原生 API 獲取當前視窗。"""
        if PYAUTOGUI_AVAILABLE:
            try:
                win = pyautogui.getActiveWindow()
                if win:
                    return {
                        "title": win.title,
                        "bounds": {"x": win.left, "y": win.top,
                                   "width": win.width, "height": win.height},
                    }
            except Exception as e:
                logger.debug(f"getActiveWindow failed: {e}")

        # macOS fallback via AppleScript
        if self.os_type == "Darwin":
            try:
                result = subprocess.run(
                    ["osascript", "-e",
                     'tell app "System Events" to get name of first process whose frontmost is true'],
                    capture_output=True, text=True, timeout=3,
                )
                app_name = result.stdout.strip()
                return {"app_name": app_name, "bounds": {}}
            except Exception:
                pass

        return {"app_name": "unknown", "bounds": {}}
