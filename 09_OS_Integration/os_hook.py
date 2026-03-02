import sys
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any

logger = logging.getLogger(__name__)

class BaseOSHook(ABC):
    """ OS 層級深度整合基底介面 """
    
    @abstractmethod
    async def get_active_window(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def monitor_clipboard(self) -> str:
        pass
        
    @abstractmethod
    async def inject_event(self, event_type: str, data: Any) -> bool:
        pass

class Windows11Hook(BaseOSHook):
    """ Windows 11 AI PC 原生整合 (利用 UIA / Win32 API) """
    async def get_active_window(self) -> Dict[str, Any]:
        # 實戰中會使用 UIAutomationClient 讀取 hwnd 與控制項樹狀圖
        logger.info("[Win11 OS Hook] 讀取作用中視窗 (Mock)")
        return {"title": "Microsoft Edge", "hwnd": 10294, "process": "msedge.exe"}

    async def monitor_clipboard(self) -> str:
        return "mock_clipboard_data_win11"
        
    async def inject_event(self, event_type: str, data: Any) -> bool:
        logger.debug(f"[Win11 OS Hook] Injecting {event_type} via SendInput")
        return True

class MacOSSequoiaHook(BaseOSHook):
    """ macOS Sequoia 整合 (利用 ApplicationServices / Accessibility API) """
    async def get_active_window(self) -> Dict[str, Any]:
        # 實戰中會呼叫 pyobjc 或 AppleScript 獲取 AXFocusedWindow
        logger.info("[macOS OS Hook] 讀取作用中視窗 (Mock)")
        return {"title": "Safari", "pid": 481, "process": "Safari"}

    async def monitor_clipboard(self) -> str:
        return "mock_clipboard_data_macos"
        
    async def inject_event(self, event_type: str, data: Any) -> bool:
        logger.debug(f"[macOS OS Hook] Injecting {event_type} via CGEventCreateMouseEvent")
        return True

class WaylandHook(BaseOSHook):
    """ Linux Wayland 整合 (利用 wlroots / wlr-wtype) """
    async def get_active_window(self) -> Dict[str, Any]:
        # Wayland 下無通用 API，依賴特定 compositor 如 swaymsg 或 hyprctl
        logger.info("[Wayland OS Hook] 讀取作用中視窗 (Mock)")
        return {"title": "Kitty - Zsh", "app_id": "kitty"}

    async def monitor_clipboard(self) -> str:
        return "mock_clipboard_data_wayland"
        
    async def inject_event(self, event_type: str, data: Any) -> bool:
        logger.debug(f"[Wayland OS Hook] Injecting {event_type} via wlr-virtual-keyboard")
        return True

def get_native_hook() -> BaseOSHook:
    """ 工廠函數：根據當前作業系統動態回傳適合的 OS Hook """
    if sys.platform == "win32":
        return Windows11Hook()
    elif sys.platform == "darwin":
        return MacOSSequoiaHook()
    else:
        return WaylandHook()
