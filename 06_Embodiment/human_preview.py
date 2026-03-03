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

    def request_approval(self, action_type: str, details: str) -> str:
        """
        提請人類審核桌面控制動作。
        回傳: 'execute', 'modify', 'cancel'
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
            return "cancel"

        print("\n請選擇你要進行的操作:")
        print("  [1] 執行 (Execute)")
        print("  [2] 修改參數 (Modify)")
        print("  [3] 取消/回滾 (Cancel)")

        while True:
            try:
                ans = input("您的選擇 [1/2/3]? ").strip().lower()
                if ans in ['1', 'e', 'execute', '']:
                    logger.info(f"✅ 人類批准 {action_type}")
                    return "execute"
                elif ans in ['2', 'm', 'modify']:
                    return "modify"
                elif ans in ['3', 'c', 'cancel']:
                    logger.warning(f"🚫 人類拒絕 {action_type}")
                    return "cancel"
                else:
                    print("無效的選擇，請輸入 1, 2, 或 3。")
            except (KeyboardInterrupt, EOFError):
                return "cancel"
