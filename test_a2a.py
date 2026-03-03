import asyncio
import logging
import sys
import os

from config_schema import AgentOSConfig
from contracts.interfaces import SubTask
from importlib import import_module
a2a_bus_mod = import_module('05_Orchestrator.a2a_bus')

# Default simple engine mock structure for test
class MockGateway:
    async def call(self, messages, agent_id, **kwargs):
        # 模擬 Agent 行為
        print(f"[MockGateway] Calling {agent_id} with kwargs: {kwargs}")
        
        if agent_id == "coder":
            # 這是被委派的子 Agent
            # 假裝第一回合有 Defect
            has_error_message = any("REJECTED" in m["content"] for m in messages if m["role"] == "user")
            if not has_error_message:
                result = "def bad_code(): pass # Defect: missing return"
            else:
                result = "def good_code(): return True"
            return {"choices": [{"message": {"content": result}}]}
            
        elif agent_id == "critic":
            # 這是審核者 Auditor
            last_message = messages[-1]["content"]
            if "bad_code" in last_message:
                result = "Missing return statement. Fix it!"
            else:
                result = "APPROVED"
                
            return {"choices": [{"message": {"content": result}}]}

class MockEngine:
    def __init__(self):
        self.gateway = MockGateway()

logging.basicConfig(level=logging.INFO)

async def test_a2a_consensus():
    print("🚀 啟動 A2A 共識網路測試")
    bus = a2a_bus_mod.A2ABus(engine=MockEngine())
    
    # 創建一個帶有預算的 SubTask
    task = SubTask(
        id="task_001",
        description="Write a simple python function that returns True",
        agent_role="coder",
        token_budget=100
    )
    
    print(f"📦 準備派發任務: {task}")
    try:
        final_result = await bus.dispatch_task(task)
        print("\n✅ 最終通過審計的結果:")
        print(final_result)
    except Exception as e:
        print(f"❌ 測試失敗: {e}")

async def test_a2a_extreme_negotiation():
    """模擬極端的 A2A 談判場景，以及多次回絕後的 Token 預算耗盡處理"""
    print("\n🚀 啟動極端 A2A 談判測試 (重試多次)")
    
    # 修改 MockGateway 行為，讓他一直失敗，確保會耗盡談判扣打或是觸動安全防線
    class StubbornGateway:
        def __init__(self):
            self.calls = 0
            
        async def call(self, messages, agent_id, **kwargs):
            self.calls += 1
            if agent_id == "coder":
                # 死都不修復
                return {"choices": [{"message": {"content": "def bad_code(): pass # STILL A DEFECT!"}}], "usage": {"prompt_tokens": 10, "completion_tokens": 50}}
            elif agent_id == "critic":
                return {"choices": [{"message": {"content": "REJECTED! Missing return!"}}], "usage": {"prompt_tokens": 20, "completion_tokens": 10}}
            return {"choices": [{"message": {"content": "ERROR"}}]}
            
    class StubbornEngine:
        def __init__(self):
            self.gateway = StubbornGateway()
            
    bus = a2a_bus_mod.A2ABus(engine=StubbornEngine())
    task = SubTask(
        id="task_fail_002",
        description="Write a simple python function that returns True",
        agent_role="coder",
        token_budget=200 # 限制預算，確保能在死循環前爆預算退出
    )
    
    print(f"📦 準備派發任務 (會陷入僵局): {task}")
    try:
        final_result = await bus.dispatch_task(task)
        print(f"\n⚠️ 拿到結果: {final_result}")
    except Exception as e:
        print(f"✅ 符合預期的崩潰攔截: {e}")

if __name__ == "__main__":
    asyncio.run(test_a2a_consensus())
    asyncio.run(test_a2a_extreme_negotiation())
