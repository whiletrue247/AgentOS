import asyncio
import logging
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../05_Orchestrator'))

from task_planner import TaskPlanner
from a2a_bus import A2ABus

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# 模擬一個特製的 Mock Gateway 供測試 (不實際花費網路)
class MockAGIGateway:
    async def call(self, messages, agent_id="default", **kwargs):
        # 模擬 Task Planner 的輸出
        if agent_id == "orchestrator" and "Objective:" in messages[-1]["content"]:
            logger.info("🤖 Mock: 模擬 Orchestrator 拆解任務")
            return {
                "choices": [{
                    "message": {
                        "content": '''[
                            {"id": "t1", "description": "Research Apple Q3 report details", "agent_role": "researcher", "depends_on": []},
                            {"id": "t2", "description": "Analyze key metrics", "agent_role": "critic", "depends_on": ["t1"]},
                            {"id": "t3", "description": "Draft the final pitch deck content", "agent_role": "writer", "depends_on": ["t2"]}
                        ]'''
                    }
                }]
            }
        
        # 模擬子 Agent 的執行
        logger.info(f"🤖 Mock: 子 Agent ({agent_id}) 正在執行任務...")
        await asyncio.sleep(0.5) # 模擬思考時間
        return {
            "choices": [{
                "message": {
                    "content": f"[MOCK RESULT from {agent_id}] Task completed successfully!"
                }
            }]
        }

async def run_e2e_orchestrator():
    logger.info("============================================================")
    logger.info("🚀 開始 Multi-Agent Orchestrator (A2A Bus) 壓力測試")
    logger.info("============================================================")
    
    class MockEngine:
        def __init__(self):
            self.gateway = MockAGIGateway()
            
    engine = MockEngine()
    
    planner = TaskPlanner(engine.gateway)
    bus = A2ABus(engine)
    
    objective = "Prepare a detailed pitch deck for Q3 Tech Review"
    
    try:
        # Phase 1: 規劃
        plan = await planner.generate_plan(objective)
        assert len(plan.tasks) == 3, "應拆解出 3 個子任務"
        
        # Phase 2: 執行 DAG
        results = await bus.run_dag(planner)
        
        logger.info("\n✅ 所有任務執行完成。最終結果彙整：")
        for task_id, res in results.items():
            logger.info(f" - [{task_id}]: {res}")
            
        assert "t3" in results, "確保最後一個依賴任務成功執行"
            
    except Exception as e:
        logger.error(f"❌ 測試失敗: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_e2e_orchestrator())
