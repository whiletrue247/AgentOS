"""
09_OS_Integration — Deep OS Hook (v5.0 SOTA)
===============================================
跨平台 OS 層級深度整合：
  - macOS: pyobjc (ApplicationServices / AppKit) + subprocess AppleScript
  - Windows: pywinauto / comtypes UIA
  - Linux: dbus (Wayland compositor messages) + xdotool fallback

每個 Hook 都有 graceful fallback：未安裝平台依賴時回傳 mock 並記錄警告。
"""

from __future__ import annotations

import logging
import subprocess
import sys
from abc import ABC, abstractmethod
from typing import Any, Dict

logger = logging.getLogger(__name__)


class BaseOSHook(ABC):
    """OS 層級深度整合基底介面"""

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
    """Windows 11 整合 (pywinauto / comtypes UIA)"""

    def __init__(self):
        self._uia = None
        try:
            import comtypes.client
            self._uia = comtypes.client.CreateObject("UIAutomationClient.CUIAutomation")
            logger.info("🪟 Windows UIA client initialized")
        except Exception:
            logger.info("🪟 Windows Hook: UIA not available, using fallback")

    async def get_active_window(self) -> Dict[str, Any]:
        if self._uia:
            try:
                root = self._uia.GetFocusedElement()
                return {
                    "title": root.CurrentName or "Unknown",
                    "class": root.CurrentClassName or "",
                    "pid": root.CurrentProcessId,
                }
            except Exception as e:
                logger.debug(f"UIA get_active_window failed: {e}")

        # Fallback: PowerShell
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "(Get-Process | Where-Object {$_.MainWindowTitle} | Select-Object -First 1).MainWindowTitle"],
                capture_output=True, text=True, timeout=3,
            )
            return {"title": result.stdout.strip() or "Unknown", "source": "powershell"}
        except Exception:
            return {"title": "Unknown", "source": "fallback"}

    async def monitor_clipboard(self) -> str:
        try:
            result = subprocess.run(
                ["powershell", "-Command", "Get-Clipboard"],
                capture_output=True, text=True, timeout=3,
            )
            return result.stdout.strip()
        except Exception:
            return ""

    async def inject_event(self, event_type: str, data: Any) -> bool:
        logger.debug(f"[Win11] Inject {event_type}: {data}")
        try:
            if event_type == "type":
                try:
                    import pywinauto.keyboard
                    pywinauto.keyboard.send_keys(str(data))
                    return True
                except ImportError:
                    script = f"$wshell = New-Object -ComObject wscript.shell; $wshell.SendKeys('{data}')"
                    subprocess.run(["powershell", "-Command", script], check=True, timeout=3)
                    return True
        except Exception as e:
            logger.error(f"Windows event injection failed: {e}")
            return False
        return True


class MacOSSequoiaHook(BaseOSHook):
    """macOS Sequoia 整合 (pyobjc ApplicationServices + AppleScript)"""

    def __init__(self):
        self._appkit = None
        try:
            from AppKit import NSWorkspace
            self._appkit = NSWorkspace
            logger.info("🍎 macOS AppKit bridge initialized")
        except ImportError:
            logger.info("🍎 macOS Hook: pyobjc not available, using AppleScript fallback")

    async def get_active_window(self) -> Dict[str, Any]:
        # Method 1: pyobjc (AppKit)
        if self._appkit:
            try:
                ws = self._appkit.sharedWorkspace()
                app = ws.frontmostApplication()
                return {
                    "app_name": app.localizedName(),
                    "bundle_id": app.bundleIdentifier(),
                    "pid": app.processIdentifier(),
                    "source": "appkit",
                }
            except Exception as e:
                logger.debug(f"AppKit get_active_window failed: {e}")

        # Method 2: AppleScript fallback
        try:
            result = subprocess.run(
                ["osascript", "-e",
                 'tell app "System Events" to get {name, unix id} of first process whose frontmost is true'],
                capture_output=True, text=True, timeout=3,
            )
            parts = result.stdout.strip().split(", ")
            return {
                "app_name": parts[0] if parts else "Unknown",
                "pid": int(parts[1]) if len(parts) > 1 else 0,
                "source": "applescript",
            }
        except Exception:
            return {"app_name": "Unknown", "source": "fallback"}

    async def monitor_clipboard(self) -> str:
        # Method 1: pyobjc
        try:
            from AppKit import NSPasteboard
            pb = NSPasteboard.generalPasteboard()
            content = pb.stringForType_("public.utf8-plain-text")
            return content or ""
        except ImportError:
            pass

        # Method 2: pbpaste
        try:
            result = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=3)
            return result.stdout
        except Exception:
            return ""

    async def inject_event(self, event_type: str, data: Any) -> bool:
        logger.debug(f"[macOS] Inject {event_type}: {data}")
        try:
            if event_type == "type":
                safe_data = str(data).replace('"', '\\"')
                subprocess.run(
                    ["osascript", "-e", f'tell application "System Events" to keystroke "{safe_data}"'],
                    check=True, timeout=3
                )
                return True
        except Exception as e:
            logger.error(f"macOS event injection failed: {e}")
            return False
        return True


class WaylandHook(BaseOSHook):
    """Linux Wayland/X11 整合 (dbus + swaymsg/hyprctl + xdotool)"""

    def __init__(self):
        self._compositor = self._detect_compositor()
        logger.info(f"🐧 Linux Hook: compositor={self._compositor}")

    @staticmethod
    def _detect_compositor() -> str:
        session = subprocess.run(
            ["echo", "$XDG_SESSION_TYPE"],
            capture_output=True, text=True, shell=True,
        ).stdout.strip()
        if "wayland" in session.lower():
            # 偵測 compositor
            for cmd in ["swaymsg", "hyprctl"]:
                try:
                    subprocess.run([cmd, "--version"], capture_output=True, timeout=2)
                    return cmd
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    pass
            return "wayland-generic"
        return "x11"

    async def get_active_window(self) -> Dict[str, Any]:
        if self._compositor == "swaymsg":
            try:
                import json
                result = subprocess.run(
                    ["swaymsg", "-t", "get_tree"],
                    capture_output=True, text=True, timeout=3,
                )
                tree = json.loads(result.stdout)
                focused = self._find_focused(tree)
                if focused:
                    return {"title": focused.get("name", ""), "app_id": focused.get("app_id", ""), "source": "sway"}
            except Exception:
                pass

        elif self._compositor == "hyprctl":
            try:
                result = subprocess.run(
                    ["hyprctl", "activewindow", "-j"],
                    capture_output=True, text=True, timeout=3,
                )
                import json
                data = json.loads(result.stdout)
                return {"title": data.get("title", ""), "class": data.get("class", ""), "source": "hyprland"}
            except Exception:
                pass

        # 嘗試使用 dbus (GNOME/KDE)
        try:
            import dbus
            bus = dbus.SessionBus()
            # GNOME Shell implementation (sometimes restricted in newer GNOME versions without extensions)
            try:
                gnome_proxy = bus.get_object('org.gnome.Shell', '/org/gnome/Shell')
                gnome_iface = dbus.Interface(gnome_proxy, 'org.gnome.Shell')
                # Evaluation of a simple javascript payload to get active window
                eval_script = """
                global.display.get_focus_window() ? global.display.get_focus_window().get_title() : ''
                """
                title, success = gnome_iface.Eval(eval_script)
                if success and title:
                    return {"title": str(title), "source": "dbus-gnome"}
            except Exception:
                pass
                
            # KDE Plasma implementation
            try:
                plasma_proxy = bus.get_object('org.kde.KWin', '/KWin')
                plasma_iface = dbus.Interface(plasma_proxy, 'org.kde.KWin')
                # ActiveWindow is a property
                title = plasma_iface.Get('org.kde.KWin', 'activeWindow', dbus_interface='org.freedesktop.DBus.Properties')
                if title:
                    return {"title": str(title), "source": "dbus-kde"}
            except Exception:
                pass
        except ImportError:
            pass

        # X11 fallback
        try:
            result = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True, text=True, timeout=3,
            )
            return {"title": result.stdout.strip(), "source": "xdotool"}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return {"title": "Unknown", "source": "fallback"}

    async def monitor_clipboard(self) -> str:
        # wl-paste (Wayland) or xclip (X11)
        for cmd in [["wl-paste"], ["xclip", "-selection", "clipboard", "-o"]]:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                return result.stdout
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
        return ""

    async def inject_event(self, event_type: str, data: Any) -> bool:
        logger.debug(f"[Linux] Inject {event_type}: {data}")
        try:
            if event_type == "type":
                # Fallback to ydotool (Wayland) or xdotool (X11)
                cmd = ["xdotool", "type", str(data)] if self._compositor == "x11" else ["ydotool", "type", str(data)]
                subprocess.run(cmd, check=True)
                return True
        except Exception as e:
            logger.error(f"Linux event injection failed: {e}")
            return False
        return True

    @staticmethod
    def _find_focused(node: dict) -> dict | None:
        """遞迴搜尋 sway tree 中 focused 的節點。"""
        if node.get("focused"):
            return node
        for child in node.get("nodes", []) + node.get("floating_nodes", []):
            result = WaylandHook._find_focused(child)
            if result:
                return result
        return None


def get_native_hook() -> BaseOSHook:
    """工廠函數：根據當前 OS 回傳對應的 Hook 實例。"""
    if sys.platform == "win32":
        return Windows11Hook()
    elif sys.platform == "darwin":
        return MacOSSequoiaHook()
    else:
        return WaylandHook()
