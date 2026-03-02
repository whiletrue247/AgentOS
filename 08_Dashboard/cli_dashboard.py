import json
import yaml
import os
import glob
from typing import Dict, Any

def load_permissions() -> Dict[str, Any]:
    config_path = os.path.join(os.getcwd(), "config/permissions.yaml")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}

def get_latest_audit_log() -> str:
    log_dir = os.path.join(os.getcwd(), "logs/test_audit")
    if not os.path.exists(log_dir):
        return None
    files = glob.glob(os.path.join(log_dir, "*.jsonl"))
    if not files:
        return None
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]

def print_dashboard():
    print("="*60)
    print("🚀 AgentOS v5.0 Command Center Dashboard")
    print("="*60)
    
    # 1. Permission Panel
    print("\n[🛡️ Fine-Grained Permissions Overview]")
    perms = load_permissions()
    roles = perms.get("roles", {})
    for role, capabilities in roles.items():
        can_shell = "✅" if capabilities.get("can_execute_shell") else "❌"
        can_net = "✅" if capabilities.get("can_access_network") else "❌"
        can_bank = "✅" if capabilities.get("can_access_bank") else "❌"
        print(f"  🧑‍💻 Role: {role.upper().ljust(12)} | Shell: {can_shell} | Net: {can_net} | Finance: {can_bank}")
        if capabilities.get("requires_human_approval"):
            print(f"      ↳ Human Approval Required for: {capabilities.get('requires_human_approval')}")

    # 2. Audit Trail
    print("\n[🕵️ Real-time Visual CoT Audit Trail]")
    log_file = get_latest_audit_log()
    if log_file:
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()[-5:] # Show last 5
                for line in lines:
                    record = json.loads(line)
                    print("-" * 50)
                    print(f"[{record['timestamp'][11:19]}] 🤖 {record['role'].upper()} (Step {record['step']})")
                    print(f"💭 Thought: {record['chain_of_thought']}")
                    print(f"🎯 Action:  {record['action']}")
                    print(f"👀 Observe: {record['observation']}")
                    if record.get('screenshot'):
                        print(f"🖼️ Screen:  {record['screenshot']}")
        except Exception as e:
            print(f"Error reading log: {e}")
    else:
        print("沒有最近的日誌。")

    print("\n[🕹️ Simulation Control]")
    print("🔘 RUN SIMULATOR (10 Steps Prediction) -> run: python 04_Engine/simulator.py")
    print("="*60)

if __name__ == "__main__":
    print_dashboard()
