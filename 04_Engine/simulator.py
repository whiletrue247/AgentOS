import logging
import asyncio
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class AgentSimulator:
    """
    Agent 模擬器
    核心功能：允許人類在按下「執行」前，要求 Agent 預判並模擬跑 N 步。
    它會使用相同的 LLM prompt，但不實際觸發 Sandbox 與 API，而是回報「預計調用的 Tool」及「預期拿到的 Observation」。
    """
    def __init__(self, engine: Any):
        self.engine = engine
        logger.info("🔮 AgentSimulator: 沙盤推演模組初始化完成")

    async def simulate_n_steps(self, task_objective: str, steps: int = 10) -> List[Dict[str, Any]]:
        """
        模擬未來 N 步的行動軌跡 (Chain of Thought 預測)
        """
        logger.info(f"🕹️ 啟動模擬器: 預測任務 '{task_objective}' 的未來 {steps} 步軌跡...")
        
        simulated_trajectory = []
        current_state = "Initial state based on user request."
        
        for step in range(1, steps + 1):
            # 實戰中：這裡會調用 Gateway (模型) 並傳入 {"dry_run": True}
            # 這裡我們用 Mock 回應演示
            await asyncio.sleep(0.1) # 模擬網路延遲
            
            # 建立假的思考流
            thought = f"[Step {step}] I need to analyze '{task_objective}'. Based on {current_state}, I will use a tool."
            proposed_action = f"search_web(query='{task_objective} context step {step}')"
            expected_result = f"Mocked search results for step {step}"
            
            simulated_node = {
                "step": step,
                "thought": thought,
                "proposed_action": proposed_action,
                "expected_observation": expected_result,
                "risk_level": "High" if "delete" in proposed_action.lower() or "rm " in proposed_action.lower() else "Low"
            }
            
            simulated_trajectory.append(simulated_node)
            current_state = f"After {proposed_action}, I observed {expected_result}"
            
            # 如果發現危險操作，標記中斷
            if simulated_node["risk_level"] == "High":
                logger.warning(f"⚠️ 模擬器在第 {step} 步偵測到高風險操作，停止推進。")
                break
                
        logger.info("🏁 沙盤推演完成。")
        return simulated_trajectory
