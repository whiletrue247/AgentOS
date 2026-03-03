"""
08_Dashboard/dashboard.py
=========================
AgentOS v5.0 可觀測性 Dashboard 2.0
使用 rich.live.Live 提供即時更新的 TUI 介面，涵蓋：
 - Audit Trail (最近操作紀錄)
 - KG Stats (知識圖譜狀態)
 - Router (模型路由與成本)
 - Agent Status (Agent 註冊狀態)
"""

from __future__ import annotations

import time
import logging
from typing import Any, Optional


from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# 初始化 Logger (避免輸出干擾畫面，這裏關閉或導向檔案)
__all__ = ["Dashboard"]

logger = logging.getLogger(__name__)

# --- 嘗試載入系統模組 ---
# 1. Audit Trail
try:
    from sys import path
    import os
    sys_path_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if sys_path_root not in path:
        path.insert(0, sys_path_root)
        
    from engine.audit_trail import get_audit_trail
    AUDIT_AVAILABLE = True
except ImportError:
    try:
        from audit_trail import get_audit_trail
        AUDIT_AVAILABLE = True
    except ImportError:
        AUDIT_AVAILABLE = False


class Dashboard:
    """可觀測性 TUI 面板，支援主子系統即時狀態注入。"""

    def __init__(
        self,
        router: Optional[Any] = None,
        kg_graph: Optional[Any] = None,
        agent_registry: Optional[Any] = None,
    ):
        self.console = Console()
        self.audit = get_audit_trail() if AUDIT_AVAILABLE else None
        self.router = router
        self.kg_graph = kg_graph
        self.agent_registry = agent_registry

    def make_audit_panel(self) -> Panel:
        table = Table(show_header=True, header_style="bold magenta", expand=True)
        table.add_column("Time", width=12)
        table.add_column("Agent", width=15)
        table.add_column("Action", width=15)
        table.add_column("Payload")
        table.add_column("Risk", width=8)
        table.add_column("Status", width=10)

        if self.audit:
            try:
                # 取得最近 10 筆
                history = self.audit.get_history(limit=10)
                for entry in history:
                    risk_color = "red" if entry.risk_level in ["high", "critical"] else "yellow" if entry.risk_level == "medium" else "green"
                    status_color = "green" if entry.result_status == "success" else "red" if entry.result_status in ["blocked", "failed", "timeout"] else "yellow"
                    table.add_row(
                        entry.timestamp[11:19],
                        entry.agent_id,
                        entry.action_type,
                        entry.payload[:40] + "..." if len(entry.payload) > 40 else entry.payload,
                        f"[{risk_color}]{entry.risk_level}[/]",
                        f"[{status_color}]{entry.result_status}[/]"
                    )
            except Exception as e:
                table.add_row("Error", "", f"Failed to load: {e}", "", "", "")
        else:
            table.add_row("-", "-", "Audit module not found", "-", "-", "-")

        return Panel(table, title="🛡️ Audit Trail (Last 10)", border_style="blue")

    def make_kg_panel(self) -> Panel:
        table = Table(show_header=False, expand=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")

        if self.kg_graph:
            try:
                stats = self.kg_graph.display_stats()
                table.add_row("Nodes", str(stats.get("nodes", 0)))
                table.add_row("Edges", str(stats.get("edges", 0)))
            except Exception:
                table.add_row("Status", "Mock / Disconnected")
                table.add_row("Nodes/Edges", "0 / 0")
        else:
            table.add_row("Status", "KG module not injected")
            table.add_row("Nodes/Edges", "N/A")

        return Panel(table, title="🧠 Knowledge Graph Stats", border_style="green")

    def make_router_panel(self) -> Panel:
        table = Table(show_header=False, expand=True)
        table.add_column("Key", style="yellow")
        table.add_column("Value", style="white")

        if self.router:
            hw = getattr(self.router, "hw_profile", None)
            npu_status = hw.recommended_local_backend if hw else "N/A"
            cost = getattr(self.router, "_session_cost_usd", 0.0)
            offline = getattr(self.router, "offline_mode", False)
            table.add_row("NPU Backend", str(npu_status))
            table.add_row("Session Cost", f"${cost:.4f} USD")
            table.add_row("Network Mode", "OFFLINE" if offline else "Hybrid (Online)")
        else:
            table.add_row("Model Router", "Not Injected")

        return Panel(table, title="🚦 Smart Router & Cost", border_style="yellow")

    def make_agent_status_panel(self) -> Panel:
        table = Table(show_header=True, header_style="bold magenta", expand=True)
        table.add_column("Agent ID")
        table.add_column("Status")
        table.add_column("Capabilities")

        if self.agent_registry:
            try:
                agents = self.agent_registry.list_agents() if hasattr(self.agent_registry, 'list_agents') else []
                for a in agents:
                    table.add_row(str(a.get('id', 'N/A')), str(a.get('status', 'idle')), str(a.get('capabilities', '')))
            except Exception:
                table.add_row("default", "[green]idle[/]", "all")
        else:
            table.add_row("default", "[green]idle[/]", "all (registry not injected)")

        return Panel(table, title="🐝 Agent Swarm Status", border_style="magenta")

    def make_layout(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="top", size=2),
            Layout(name="middle", ratio=2),
            Layout(name="bottom", ratio=1)
        )
        layout["middle"].split_row(
            Layout(name="audit", ratio=2),
            Layout(name="status", ratio=1)
        )
        layout["status"].split_column(
            Layout(name="kg"),
            Layout(name="router")
        )

        title = Text("🚀 AgentOS v5.0 Dashboard", justify="center", style="bold white on blue")
        layout["top"].update(Panel(title))
        
        layout["audit"].update(self.make_audit_panel())
        layout["status"]["kg"].update(self.make_kg_panel())
        layout["status"]["router"].update(self.make_router_panel())
        layout["bottom"].update(self.make_agent_status_panel())
        
        return layout

    def run(self, refresh_rate: float = 2.0):
        with Live(self.make_layout(), refresh_per_second=1/refresh_rate, screen=True) as live:
            try:
                while True:
                    time.sleep(refresh_rate)
                    live.update(self.make_layout())
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    app = Dashboard()
    app.run()
