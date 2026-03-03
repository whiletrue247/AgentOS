"""
05_Orchestrator — CrewAI Roles Integration (v5.0 SOTA)
======================================================
整合 CrewAI 作為 LangGraph 之外的第二種協同選項。
讀取 SOUL.md / SubTask，分派 Persona，執行 Sequential Process 任務。
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

try:
    from crewai import Agent, Task, Crew, Process
    CREWAI_AVAILABLE = True
except ImportError:
    CREWAI_AVAILABLE = False
    logger.info("ℹ️ crewai not installed — CrewAI role integration disabled")


class CrewAIBuilder:
    """建構 CrewAI 代理團隊與任務分配"""
    
    def __init__(self, engine: Any):
        self.engine = engine
        
    def build_agent(self, role_name: str, goal: str, backstory: str) -> "Agent":
        if not CREWAI_AVAILABLE:
            raise ImportError("crewai is required")
            
        # 注意: 實際整合中，LLM 需要傳遞給 CrewAI 的 llm 參數
        # 這裡為了展示概念，若未裝 langhain-lite，我們先使用預設
        
        # CrewAI 預設使用 langchain compatible 模型
        # 這邊創建一個 Agent
        return Agent(
            role=role_name,
            goal=goal,
            backstory=backstory,
            verbose=True,
            allow_delegation=False,
            # llm=your_llm_instance
        )

    def build_task(self, description: str, expected_output: str, agent: "Agent") -> "Task":
        if not CREWAI_AVAILABLE:
            raise ImportError("crewai is required")
            
        return Task(
            description=description,
            expected_output=expected_output,
            agent=agent
        )

    def build_crew(self, agents: List["Agent"], tasks: List["Task"]) -> "Crew":
        if not CREWAI_AVAILABLE:
            raise ImportError("crewai is required")
            
        return Crew(
            agents=agents,
            tasks=tasks,
            process=Process.sequential,  # 預設循序執行
            verbose=True
        )


async def run_crewai_dag(planner: Any, engine: Any) -> Dict[str, str]:
    """
    接收 planner，將其任務轉換為 CrewAI 的任務與 Agent 並執行。
    """
    if not CREWAI_AVAILABLE:
        raise ImportError("crewai package is not installed.")
        
    builder = CrewAIBuilder(engine)
    crew_agents = {}
    crew_tasks = []
    
    # 建立 Agents (從任務中的 agent_role 取得)
    for t in planner.current_plan.tasks:
        role = t.agent_role
        if role not in crew_agents:
            crew_agents[role] = builder.build_agent(
                role_name=role,
                goal=f"Complete tasks effectively as {role}",
                backstory=f"You are an expert {role} in the AgentOS multi-agent system."
            )
            
        task_obj = builder.build_task(
            description=t.description,
            expected_output="Detailed execution result.",
            agent=crew_agents[role]
        )
        task_obj.id = t.id # monkey patch
        crew_tasks.append(task_obj)
        
    crew = builder.build_crew(list(crew_agents.values()), crew_tasks)
    
    logger.info("👥 Starting CrewAI kickoff process...")
    # CrewAI kickoff is blocking usually, but we run it in async compatible way if needed
    # for demo we just call kickoff
    result = crew.kickoff()
    
    logger.info("🏁 CrewAI workflow finished. Global result summarized.")
    
    # 回填結果到字典 (CrewAI Task 沒直接回傳 per-task, 我們模擬回傳最後結果)
    results = {}
    for t in crew_tasks:
        results[t.id] = getattr(t, "output", {}).get("raw_output", "") or str(result)
        
    # 同步回 planner
    for t in planner.current_plan.tasks:
        planner.update_task_status(t.id, "completed", results.get(t.id, ""))
        
    return results
