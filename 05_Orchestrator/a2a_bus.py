import logging
import asyncio
from typing import Any, Dict, List, Optional
from task_planner import SubTask
from sub_agents import get_role_prompt

logger = logging.getLogger(__name__)

class A2ABus:
    """
    Agent-to-Agent Event Bus.
    負責將 Planner 規劃出來的 SubTask，派發給對應角色 (編譯專屬 Prompt)，
    並透過 Engine Loop / Gateway 執行，最後回收結果給 Orchestrator 參考。
    """

    def __init__(self, engine: Any):
        # 這裡持有 main engine 或 gateway 的引用，以便觸發真實的 inference 迴圈
        self.engine = engine

    async def dispatch_task(self, task: SubTask, global_context: str = "") -> str:
        """
        向指定的 sub-agent 派發任務。
        global_context: 整個專案或父任務的大致背景，避免子任務失去方向感。
        """
        logger.info(f"🚌 A2ABus: Dispatching Task [{task.id}] -> {task.agent_role}")
        
        system_prompt = get_role_prompt(task.agent_role)
        
        if global_context:
             system_prompt += f"\n\n[GLOBAL CONTEXT]\n{global_context}"
             
        # 構造給這個子 Agent 的專屬對話紀錄
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Your task:\n{task.description}"}
        ]
        
        # 在系統架構中，如果我們有對接 04_Engine 的 `run_once` 或 `_agent_loop`，
        # 應該直接呼叫它，讓它處理 tool calling。
        # 這裡我們為了確保子 Agent 可以用 tools，直接呼叫 engine 內建的方法
        # (需要確認 Engine 介命是否可以傳入自訂 messages 與 agent_id)
        
        # 為了架構靈活性，我們透過 engine 的 gateway 直接打，
        # TODO: 實作完整的 "spawn_agent" API 來讓 SubAgent 也擁有自己的 Memory 實體
        # 這裡作為 Phase 1 的第一版，直接過 Gateway (只能打單輪，不含工具迴圈)
        
        try:
            # 這裡呼叫 Gateway，且帶入 task.agent_role 作為 agent_id，
            # 這樣 SmartRouter 就會根據 config 給它合適的模型 (例如 coder_model, writer_model)
            response = await self.engine.gateway.call(
                messages=messages,
                agent_id=task.agent_role
            )
            
            result = response["choices"][0]["message"]["content"]
            logger.info(f"✅ A2ABus: Task [{task.id}] completed by {task.agent_role}.")
            return result
            
        except Exception as e:
            logger.error(f"❌ A2ABus: Task [{task.id}] failed. Reason: {e}")
            raise

    async def run_dag(self, planner: Any) -> Dict[str, str]:
        """
        自動執行任務圖 (DAG)。
        - 找出 runnable 的任務
        - 丟進 asyncio.gather 做平行執行
        - 收集結果後更新 planner 狀態
        - 直到所有 tasks 做完
        """
        results = {}
        
        while True:
            runnable_tasks = planner.get_next_runnable_tasks()
            
            if not runnable_tasks:
                # 檢查是否全部完成了
                all_done = all(t.status in ["completed", "failed"] for t in planner.current_plan.tasks)
                if all_done:
                    break
                else:
                    # 如果還有沒做完的但沒有 runnable，代表可能發生 deadlock (依賴的任務 failed 或依賴寫錯)
                    logger.error("🚨 DAG Deadlock! Unfinished tasks exist but none are runnable.")
                    break
                    
            tasks_coros = []
            for t in runnable_tasks:
                t.status = "in_progress"
                tasks_coros.append(self._execute_single_task(planner, t))
                
            await asyncio.gather(*tasks_coros)
            
        return {t.id: t.result for t in planner.current_plan.tasks if t.result}

    async def _execute_single_task(self, planner: Any, task: SubTask):
        try:
            # 這裡把已經跑完的依賴結果當作 context 塞給它
            context_str = "Completed dependencies:\n"
            for dep_id in task.depends_on:
                dep_task = next(t for t in planner.current_plan.tasks if t.id == dep_id)
                context_str += f"- [{dep_id}] Result: {dep_task.result[:500]}...\n" # 截斷避免太長
                
            result = await self.dispatch_task(task, global_context=context_str)
            planner.update_task_status(task.id, "completed", result)
        except Exception:
             planner.update_task_status(task.id, "failed")
