"""
06_Embodiment — Human Preview UI (v5.0 SOTA)
==============================================
當 Agent 試圖控制滑鼠鍵盤時，若啟動 require_approval，
則將截圖或動作坐標傳送至這裡，由人類審核放行 (Human-in-the-Loop)。
"""

from __future__ import annotations

import logging
import sys

from rich.console import Console
from rich.panel import Panel

__all__ = ["HumanPreviewUI"]

logger = logging.getLogger(__name__)


class HumanPreviewUI:
    """提供終端機或外部可視化介面請求人類控制授權。"""

    def __init__(self):
        self.console = Console()

    def request_approval(self, action_type: str, details: str) -> bool:
        """
        提請人類審核桌面控制動作。
        回傳 True 代表放行，False 代表阻斷。
        """
        self.console.print(Panel(
            f"[bold yellow]⚠️ Agent 請求桌面控制權限[/]\n\n"
            f"[bold cyan]動作類型:[/] {action_type}\n"
            f"[bold cyan]詳細參數:[/] {details}\n\n"
            "[dim]此操作將真實移動您的滑鼠或敲擊鍵盤。[/]",
            title="Human Preview (06_Embodiment)", border_style="yellow"
        ))

        if not sys.stdin.isatty():
            # 無法互動時預設阻斷
            logger.warning("⚠️ 非互動環境，拒絕桌面控制。")
            return False

        try:
            ans = input("批准此動作？ (Y/n): ").strip().lower()
            if ans in ['', 'y', 'yes']:
                logger.info(f"✅ 人類批准 {action_type}")
                return True
            logger.warning(f"🚫 人類拒絕 {action_type}")
            return False
        except (KeyboardInterrupt, EOFError):
            return False
