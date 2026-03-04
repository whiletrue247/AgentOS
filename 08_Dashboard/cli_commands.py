"""
08_Dashboard/cli_commands.py
============================
AgentOS CLI Commands (simulate, audit)
提供與模擬器、稽核追蹤模組介接的豐富終端機體驗。
"""

import argparse
import asyncio
import sys
import os

from rich.console import Console
from rich.table import Table
from rich.markdown import Markdown

# 設定相對路徑以引入其他模組
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 嘗試載入系統模組
try:
    from engine.simulator import AgentSimulator
    from engine.audit_trail import get_audit_trail
    from orchestrator.task_planner import TaskPlanner
    from orchestrator.a2a_bus import A2ABus
except ImportError:
    try:
        from simulator import AgentSimulator
        from audit_trail import get_audit_trail
        import importlib
        task_planner_mod = importlib.import_module("05_Orchestrator.task_planner")
        TaskPlanner = task_planner_mod.TaskPlanner
        a2a_bus_mod = importlib.import_module("05_Orchestrator.a2a_bus")
        A2ABus = a2a_bus_mod.A2ABus
    except ImportError:
        AgentSimulator = None
        get_audit_trail = None
        TaskPlanner = None
        A2ABus = None


class DummyGateway:
    """為了在缺少真實 Engine 環境下仍能測試指令而設計的 Dummy Gateway"""
    async def call(self, messages, agent_id, temperature=0.3):
        import json
        return {
            "choices": [{
                "message": {
                    "content": json.dumps([
                        {"step": 1, "thought": "Analyzing objective...", "proposed_action": "search_web('how to')", "expected_observation": "Results found", "risk_level": "low", "estimated_tokens": 120},
                        {"step": 2, "thought": "Executing system command...", "proposed_action": "rm -rf /tmp/cache", "expected_observation": "Cache cleared", "risk_level": "high", "estimated_tokens": 180}
                    ])
                }
            }]
        }

class DummyEngine:
    def __init__(self):
        self.gateway = DummyGateway()


async def simulate_cmd(objective: str):
    console = Console()
    console.print(f"[bold cyan]🔍 Starting Simulation for:[/] {objective}")
    
    if AgentSimulator is None:
        console.print("[red]Error: AgentSimulator module not found.[/]")
        return

    # 在真實環境中應替換為 Kernel 的 Engine，這裡使用 DummyEngine 展示
    engine = DummyEngine()
    simulator = AgentSimulator(engine)
    
    trajectory = await simulator.simulate_n_steps(objective, steps=10)
    
    table = Table(title="🔮 Predicted Execution Trajectory", expand=True)
    table.add_column("Step", justify="right", style="cyan", no_wrap=True)
    table.add_column("Thought", style="magenta")
    table.add_column("Action", style="green")
    table.add_column("Risk", justify="center")
    
    high_risk_count = 0
    total_tokens = 0
    
    for step in trajectory:
        risk = step.get("risk_level", "low")
        if risk == "high":
            risk_str = "[bold red]HIGH[/]"
            high_risk_count += 1
        elif risk == "medium":
            risk_str = "[bold yellow]MED[/]"
        else:
            risk_str = "[green]LOW[/]"
            
        action = step.get("proposed_action", "")
        if risk == "high":
            action = f"[bold red]{action}[/]"
            
        total_tokens += int(step.get("estimated_tokens", 0))
        
        table.add_row(
            str(step.get("step")),
            step.get("thought", ""),
            action,
            risk_str
        )
        
    console.print(table)
    console.print(f"\n[bold]📊 Summary:[/] Total Tokens: {total_tokens} | High Risk Steps: {high_risk_count}")
    
    if high_risk_count > 0:
        console.print("\n[bold red]⚠️  WARNING: High risk actions detected in simulation![/]")
        if sys.stdin.isatty():
            confirm = input("Do you want to proceed with execution? (y/N): ")
            if confirm.lower() != 'y':
                console.print("[yellow]Execution aborted by user.[/]")
                sys.exit(0)
        else:
            console.print("[yellow]Non-Interactive Mode: Automatically pausing due to high risk.[/]")
            
    console.print("\n[green]✅ Simulation approved. Ready for execution.[/]")


def audit_cmd(days: int):
    console = Console()
    if get_audit_trail is None:
        console.print("[red]Error: Audit trail module not found.[/]")
        return
        
    try:
        audit = get_audit_trail()
        report = audit.export_report(date_range=days)
        md = Markdown(report)
        console.print(md)
    except Exception as e:
        console.print(f"[red]Error generating audit report:[/] {e}")


def flow_cmd(objective: str):
    console = Console()
    console.print(f"[bold cyan]🕸️  Generating FlowBuilder Topology for:[/] {objective}")
    
    if TaskPlanner is None or A2ABus is None:
        console.print("[red]Error: Orchestrator modules not found. Ensure 05_Orchestrator is accessible.[/]")
        return
        
    try:
        planner = TaskPlanner()
        # 產生計畫
        import asyncio
        asyncio.run(planner.plan_objective(objective))
        
        bus = A2ABus(engine=DummyEngine())
        mermaid_str = bus.export_topology_mermaid(planner, title=f"Flow: {objective}")
        
        # 寫入到檔案
        output_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs", "flow_diagram.md"))
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"# AgentOS FlowBuilder Preview\n\n> Objective: {objective}\n\n{mermaid_str}\n")
            
        console.print(f"[green]✅ Topology exported to [bold]{output_path}[/bold][/]")
        console.print("\n[dim]Preview:[/dim]")
        
        # 在終端機也印出一份
        md = Markdown(mermaid_str)
        console.print(md)
        
    except Exception as e:
        console.print(f"[red]Error generating flow topology:[/] {e}")

def main():
    parser = argparse.ArgumentParser(description="AgentOS CLI Commands")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    sim_parser = subparsers.add_parser("simulate", help="Simulate agent execution for an objective")
    sim_parser.add_argument("objective", type=str, help="The goal to simulate")
    
    audit_parser = subparsers.add_parser("audit", help="Generate security audit report")
    audit_parser.add_argument("--days", type=int, default=7, help="Number of days to include in report")
    
    flow_parser = subparsers.add_parser("flow", help="Export Agent topology as Mermaid DAG")
    flow_parser.add_argument("objective", type=str, help="The goal to build the flow for")
    
    args = parser.parse_args()
    
    if args.command == "simulate":
        asyncio.run(simulate_cmd(args.objective))
    elif args.command == "audit":
        audit_cmd(args.days)
    elif args.command == "flow":
        flow_cmd(args.objective)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
