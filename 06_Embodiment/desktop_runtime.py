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
from pathlib import Path
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
    
    動作風險分級：
      L0 (無風險): scroll, get_active_window_info → 無截圖無確認
      L1 (低風險): click, type_text → require_approval 時才確認
      L2 (高風險): press_key + 破壞性修飾鍵 → 強制截圖 + audit trail
    """

    # L2 高危鍵 (強制截圖)
    _HIGH_RISK_KEYS = frozenset({
        "delete", "backspace", "return", "enter",
        "tab",  # 可在終端機執行 auto-complete
    })
    _HIGH_RISK_MODIFIERS = frozenset({
        "command", "cmd", "ctrl", "control", "super", "win",
    })

    def __init__(self, require_approval: bool = False):
        self.os_type = platform.system()
        self.require_approval = require_approval
        self.preview_ui = None
        if self.require_approval:
            try:
                from .human_preview import HumanPreviewUI
                self.preview_ui = HumanPreviewUI()
            except ImportError:
                from human_preview import HumanPreviewUI
                self.preview_ui = HumanPreviewUI()
        
        # Audit trail 截圖目錄
        self._audit_dir = Path("/tmp/agentos_audit_screenshots")
        self._audit_dir.mkdir(parents=True, exist_ok=True)
        
        backend = "pyautogui" if PYAUTOGUI_AVAILABLE else "mock"
        logger.info(f"🖥️ DesktopRuntime: os={self.os_type}, backend={backend}, approval={require_approval}")

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
        if self.preview_ui and not self.preview_ui.request_approval("Mouse Click", f"({x}, {y}) Button: {button}"):
            logger.warning(f"🚫 拒絕 Click: {button} at ({x}, {y})")
            return
            
        if PYAUTOGUI_AVAILABLE:
            pyautogui.click(x=x, y=y, button=button)
            logger.info(f"🖱️ Clicked: {button} at ({x}, {y})")
        else:
            logger.info(f"🖱️ [MOCK] Click: {button} at ({x}, {y})")

    def double_click(self, x: int, y: int):
        """雙擊"""
        if self.preview_ui and not self.preview_ui.request_approval("Mouse Double Click", f"({x}, {y})"):
            logger.warning(f"🚫 拒絕 Double Click: ({x}, {y})")
            return
            
        if PYAUTOGUI_AVAILABLE:
            pyautogui.doubleClick(x=x, y=y)
            logger.info(f"🖱️ Double-clicked at ({x}, {y})")
        else:
            logger.info(f"🖱️ [MOCK] Double-click at ({x}, {y})")

    def scroll(self, clicks: int, x: Optional[int] = None, y: Optional[int] = None):
        """滾輪"""
        x_str = x if x is not None else "current"
        y_str = y if y is not None else "current"
        if self.preview_ui and not self.preview_ui.request_approval("Mouse Scroll", f"Clicks: {clicks} at ({x_str}, {y_str})"):
            logger.warning(f"🚫 拒絕 Scroll: {clicks} clicks")
            return
            
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
        if self.preview_ui and not self.preview_ui.request_approval("Keyboard Typing", f"Text: '{text}'"):
            logger.warning(f"🚫 拒絕 Typing: {text}")
            return
            
        if PYAUTOGUI_AVAILABLE:
            pyautogui.write(text, interval=interval)
            logger.info(f"⌨️ Typed: {text[:20]}...")
        else:
            logger.info(f"⌨️ [MOCK] Type: {text[:20]}...")

    def press_key(self, key_name: str, modifiers: Optional[list] = None):
        """模擬按下快捷鍵 (如 enter, escape, cmd+c)。L2 高危鍵強制截圖。"""
        mod_str = "+".join(modifiers) + "+" if modifiers else ""
        is_l2 = self._is_high_risk_key(key_name, modifiers)
        
        # L2 高危：強制截圖 audit trail
        if is_l2:
            screenshot_path = self._forced_screenshot_audit(f"press_{mod_str}{key_name}")
            logger.warning(f"🔴 [L2 高危] press_key: {mod_str}{key_name} — 截圖已存: {screenshot_path}")
        
        # 確認機制 (L1: require_approval / L2: 強制)
        if self.preview_ui and (self.require_approval or is_l2):
            screenshot_path = getattr(self, '_last_audit_screenshot', None)
            if not self.preview_ui.request_approval(
                "Keyboard Press" + (" [⚠️ HIGH RISK]" if is_l2 else ""),
                f"Key: {mod_str}{key_name}",
                screenshot_path=screenshot_path,
            ):
                logger.warning(f"🚫 拒絕 Press: {mod_str}{key_name}")
                return
            
        if PYAUTOGUI_AVAILABLE:
            if modifiers:
                pyautogui.hotkey(*modifiers, key_name)
            else:
                pyautogui.press(key_name)
            logger.info(f"⌨️ Pressed: {mod_str}{key_name}")
        else:
            mod_str = "+".join(modifiers) + "+" if modifiers else ""
            logger.info(f"⌨️ [MOCK] Press: {mod_str}{key_name}")

    # ----------------------------------------------------------
    # Risk Classification Helpers
    # ----------------------------------------------------------
    @classmethod
    def _is_high_risk_key(cls, key_name: str, modifiers: Optional[list] = None) -> bool:
        """判斷鍵盤操作是否為 L2 高危。"""
        key_lower = key_name.lower()
        
        # 高危鍵（無需修飾鍵）
        if key_lower in cls._HIGH_RISK_KEYS:
            return True
        
        # 任何帶有高危修飾鍵的組合
        if modifiers:
            for mod in modifiers:
                if mod.lower() in cls._HIGH_RISK_MODIFIERS:
                    return True
        
        return False

    def _forced_screenshot_audit(self, action_label: str) -> str:
        """強制截圖並存入 audit trail 目錄。回傳截圖路徑。"""
        import time as _time
        timestamp = _time.strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{action_label}.png"
        save_path = str(self._audit_dir / filename)
        
        self.take_screenshot(save_path=save_path)
        self._last_audit_screenshot = save_path
        return save_path

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
