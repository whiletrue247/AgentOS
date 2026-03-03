import json
import logging
from typing import List, Any, Optional

from contracts.interfaces import SubTask, Plan

logger = logging.getLogger(__name__)
    
class TaskPlanner:
    """
    負責將大型目標拆解成 DAG (Directed Acyclic Graph) 的子任務。
    在實際應用中，它會呼叫 LLM (Orchestrator) 產生這些拆解步驟，
    並負責追蹤進度與自動重排。
    """
    
    def __init__(self, gateway: Any):
        self.gateway = gateway
        self.current_plan: Optional[Plan] = None

    async def generate_plan(self, objective: str) -> Plan:
        """呼叫高智商 LLM 把任務拆掉"""
        logger.info(f"🧠 TaskPlanner: 正在拆解巨型任務 -> {objective}")
        
        system_prompt = """
        You are a Master Orchestrator. The user will give you a massive objective.
        You must break it down into a DAG (Directed Acyclic Graph) of sub-tasks.
        Respond ONLY with a valid JSON array of tasks. Each task must have:
        - "id": string
        - "description": string
        - "agent_role": string (choose from "researcher", "coder", "writer", "critic")
        - "depends_on": array of string (IDs of tasks that must be done first)
        - "token_budget": integer (estimated maximum tokens budget for this step, e.g. 500, 1000, 4000)
        """
        
        # 呼叫大腦 (自動透過 SmartRouter 轉到 Orchestrator)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Objective: {objective}"}
        ]
        
        # 這裡會由 router 自動配對最聰明的模型 (如 gpt-4o 或 claude-3-5)
        response = await self.gateway.call(messages=messages, agent_id="orchestrator")
        
        reply_content = response["choices"][0]["message"]["content"]
        
        # 簡易的 JSON 解析 (實戰中需更強健的容錯機制)
        try:
            # 清除 markdown code block markers
            if "```json" in reply_content:
                reply_content = reply_content.split("```json")[1].split("```")[0].strip()
            elif "```" in reply_content:
                reply_content = reply_content.split("```")[1].split("```")[0].strip()
            
            task_list = json.loads(reply_content)
            
            sub_tasks = []
            for t in task_list:
                sub_tasks.append(SubTask(
                    id=t.get("id", ""),
                    description=t.get("description", ""),
                    agent_role=t.get("agent_role", "default"),
                    depends_on=t.get("depends_on", []),
                    token_budget=t.get("token_budget", 0)
                ))
            
            self.current_plan = Plan(objective=objective, tasks=sub_tasks)
            
            logger.info(f"✅ 任務拆解完成！共產生 {len(sub_tasks)} 個子階段。")
            return self.current_plan

        except Exception as e:
            logger.error(f"❌ 拆解計畫解析失敗: {e}")
            raise Exception("Failed to generate actionable plan")

    def get_next_runnable_tasks(self) -> List[SubTask]:
        """找出所有 depends_on 都已經 completed 的 pending 任務"""
        if not self.current_plan:
            return []
            
        completed_ids = {t.id for t in self.current_plan.tasks if t.status == "completed"}
        
        runnable = []
        for t in self.current_plan.tasks:
            if t.status == "pending":
                if all(dep in completed_ids for dep in t.depends_on):
                    runnable.append(t)
                    
        return runnable

    def update_task_status(self, task_id: str, status: str, result: Optional[str] = None):
        """更新任務狀態"""
        if not self.current_plan:
            return
            
        for t in self.current_plan.tasks:
            if t.id == task_id:
                t.status = status
                if result:
                    t.result = result
                logger.debug(f"📋 Task [{task_id}] 狀態更新 -> {status}")
                break
