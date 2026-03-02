import asyncio
import logging
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import importlib.util
def load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    if spec and spec.loader:
        spec.loader.exec_module(mod)
    return mod

sim_mod = load_mod("simulator", os.path.join(os.path.dirname(__file__), "..", "04_Engine", "simulator.py"))
AgentSimulator = sim_mod.AgentSimulator

audit_mod = load_mod("audit_trail", os.path.join(os.path.dirname(__file__), "..", "08_Dashboard", "audit_trail.py"))
AuditTrail = audit_mod.AuditTrail

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

async def run_audit_simulator_test():
    logger.info("============================================================")
    logger.info("🕵️ 開始 Simulator & Audit Trail (Phase 5) 基礎測試")
    logger.info("============================================================")
    
    # 測試 1: 模擬器
    logger.info("\n--- 測試 1: Agent Simulator 預測 N 步 軌跡 ---")
    
    class MockEngine:
        pass
        
    simulator = AgentSimulator(engine=MockEngine())
    task_goal = "Buy a plane ticket to Tokyo and find a hotel near Shinjuku"
    
    # 要求它跑 5 步預測
    predicted_path = await simulator.simulate_n_steps(task_goal, steps=5)
    logger.info("\n[模擬推演結果 (Dry Run)]:")
    for node in predicted_path:
        logger.info(f"  > Step {node['step']}: {node['thought']}")
        logger.info(f"    Action: {node['proposed_action']} -> Obs: {node['expected_observation']}")
    
    assert len(predicted_path) == 5, "模擬器應該確實產出 5 步的預測軌跡"
    logger.info("✅ AgentSimulator 預測邏輯正常")

    # 測試 2: Audit Trail 稽核紀錄
    logger.info("\n--- 測試 2: Visual CoT Audit Trail 追蹤器 ---")
    audit = AuditTrail(log_dir="logs/test_audit")
    
    # 紀錄兩步
    audit.log_step(
        role="researcher", 
        step_index=1, 
        thought="I should search for flights first.",
        action={"tool": "browser_cdp", "url": "skyscanner.com"},
        observation="List of flights from TPE to NRT loaded."
    )
    
    audit.log_step(
        role="orchestrator", 
        step_index=2, 
        thought="Now booking the hotel near Shinjuku using the desktop app.",
        action={"tool": "desktop_click", "x": 100, "y": 200},
        observation="Hotel booking confirmed.",
        screenshot_path="/tmp/screenshot_step2.png"
    )
    
    trail = audit.get_recent_trail()
    logger.info(f"💾 歷史軌跡讀取 ({len(trail)} records):")
    for rec in trail:
        logger.info(rec)
        
    assert len(trail) == 2, "沒有順利讀取出存檔的 2 步紀錄"
    assert trail[1]["screenshot"] == "/tmp/screenshot_step2.png"
    logger.info("✅ AuditTrail 存取邏輯正常")

if __name__ == "__main__":
    asyncio.run(run_audit_simulator_test())
