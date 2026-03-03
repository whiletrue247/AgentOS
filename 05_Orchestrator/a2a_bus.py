"""
05_Orchestrator — Agent-to-Agent Bus (v5.0 SOTA — LangGraph + Swarm)
=====================================================================
使用 LangGraph StateGraph 實現多 Agent 編排：
  - TypedDict 定義圖狀態
  - 條件邊 (Conditional Edges) 支援任務路由
  - Human-in-the-Loop 審核節點
  - DAG 拓撲排序執行
  - Hierarchical Swarm 支援 (從單層 DAG 過度到多層 Agent 階層)

當 langgraph 不可用時，退回 asyncio.gather() 手動 DAG。
"""

from __future__ import annotations

import asyncio
import enum
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# ============================================================
# Swarm Mode
# ============================================================

class SwarmMode(enum.Enum):
    """多 Agent 執行模式"""
    FLAT = "flat"                    # 單層 DAG（預設）
    HIERARCHICAL = "hierarchical"    # 階層式 Swarm（過度委派）


# 最大過度深度（防無限遞迴）
MAX_SWARM_DEPTH = 3

# 嘗試載入 LangGraph
try:
    from langgraph.graph import StateGraph, START, END
    from typing import TypedDict, Annotated
    import operator
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    logger.info("ℹ️ langgraph not installed — using asyncio fallback for DAG execution")

# 嘗試載入本地模組
try:
    from .task_planner import SubTask
    from .sub_agents import get_role_prompt
except ImportError:
    from task_planner import SubTask
    from sub_agents import get_role_prompt

# 嘗試載入 CrewAI 角色擴展
try:
    from .crewai_roles import CREWAI_AVAILABLE, run_crewai_dag
except ImportError:
    try:
        from crewai_roles import CREWAI_AVAILABLE, run_crewai_dag
    except ImportError:
        CREWAI_AVAILABLE = False


# ============================================================
# LangGraph State Schema
# ============================================================

if LANGGRAPH_AVAILABLE:
    class OrchestratorState(TypedDict):
        """LangGraph 圖狀態"""
        objective: str
        tasks: List[dict]
        completed: Annotated[List[str], operator.add]  # 已完成的 task IDs
        results: Dict[str, str]
        human_approved: bool
        current_batch: List[str]    # 當前批次執行的 task IDs


class A2ABus:
    """
    Agent-to-Agent Event Bus (v5.0 SOTA + Swarm).
    LangGraph 模式：使用 StateGraph 組織 Plan → Execute → Review 的圖流程。
    Hierarchical 模式：複雜子任務可遞迴委派給子 Swarm。
    Fallback 模式：使用 asyncio.gather 做直接 DAG 排程。
    """

    def __init__(self, engine: Any, depth: int = 0):
        self.engine = engine
        self._depth = depth  # 當前 Swarm 深度
        if depth > 0:
            logger.info(f"🔄 A2ABus 子 Swarm 延伸 (depth={depth}/{MAX_SWARM_DEPTH})")

    # ----------------------------------------------------------
    # 核心：執行單個子任務
    # ----------------------------------------------------------
    async def dispatch_task(self, task: SubTask, global_context: str = "") -> str:
        """向指定的 sub-agent 派發任務，支援 A2A 共識網路 (協商與多簽審核)。"""
        logger.info(f"🚌 A2ABus: Dispatching Task [{task.id}] → {task.agent_role}")

        # 第一階段：準備 System Prompt
        system_prompt = get_role_prompt(task.agent_role)
        if global_context:
            system_prompt += f"\n\n[GLOBAL CONTEXT]\n{global_context}"
            
        # 加入財務預算感知 (Token Economy)
        budget_instruction = ""
        if hasattr(task, 'token_budget') and task.token_budget:
            budget_instruction = f"\n\n[ECONOMY]\nYou have a strict budget of {task.token_budget} tokens. Be extremely concise and efficient."

        messages = [
            {"role": "system", "content": system_prompt + budget_instruction},
            {"role": "user", "content": f"Your task:\n{task.description}"},
        ]

        max_negotiation_turns = 3
        current_turn = 0
        
        while current_turn < max_negotiation_turns:
            try:
                # 階段二：子 Agent 執行與提案 (Execution & Proposal)
                # 強制附加 max_tokens 限制以防範預算超標
                call_kwargs = {
                    "messages": messages,
                    "agent_id": task.agent_role,
                }
                if hasattr(task, 'token_budget') and task.token_budget and task.token_budget > 0:
                    call_kwargs["max_tokens"] = task.token_budget

                response = await self.engine.gateway.call(**call_kwargs)
                result = response["choices"][0]["message"]["content"]
                
                # 階段三：多簽審計 (Multi-signature Audit)
                # 假設這裡固定透過 Critic 角色來進行雙重確認 (Double Check)
                audit_prompt = get_role_prompt("critic")
                audit_messages = [
                    {"role": "system", "content": audit_prompt},
                    {"role": "user", "content": f"Task Description:\n{task.description}\n\nProposed Result from {task.agent_role}:\n{result}\n\nEvaluate if the result strictly and safely fulfills the task. Reply with 'APPROVED' or list the specific defects."}
                ]
                
                logger.info(f"⚖️ A2ABus: Submitting result of [{task.id}] for Multi-Sig Audit...")
                audit_response = await self.engine.gateway.call(
                    messages=audit_messages,
                    agent_id="critic",
                )
                audit_result = audit_response["choices"][0]["message"]["content"].strip()
                
                if "APPROVED" in audit_result.upper():
                    logger.info(f"✅ A2ABus: Task [{task.id}] completed & APPROVED by Auditor.")
                    return result
                else:
                    logger.warning(f"⚠️ A2ABus: Task [{task.id}] REJECTED by Auditor. Reason:\n{audit_result}")
                    current_turn += 1
                    # 階段四：交涉與重試 (Negotiation & Retry)
                    messages.append({"role": "assistant", "content": result})
                    messages.append({"role": "user", "content": f"Your previous result was REJECTED by the Auditor.\nFeedback: {audit_result}\n\nPlease fix the defects and submit a revised result."})
                    
            except Exception as e:
                logger.error(f"❌ A2ABus: Task [{task.id}] failed during execution/audit: {e}")
                raise

        raise RuntimeError(f"Task [{task.id}] failed to reach consensus after {max_negotiation_turns} negotiation turns.")

    # ----------------------------------------------------------
    # LangGraph DAG Execution
    # ----------------------------------------------------------
    def build_graph(self, planner: Any):
        """
        使用 LangGraph StateGraph 建構任務流程圖。
        流程: plan_node → [human_review] → execute_batch → check_completion → (loop or end)
        """
        if not LANGGRAPH_AVAILABLE:
            raise ImportError("langgraph is required for graph-based execution")

        graph = StateGraph(OrchestratorState)

        # === Nodes ===
        async def plan_node(state: OrchestratorState) -> dict:
            """找出當前可執行的任務批次"""
            tasks = state["tasks"]
            completed = set(state.get("completed", []))
            batch = []
            for t in tasks:
                if t["id"] not in completed and t.get("status") != "failed":
                    deps = set(t.get("depends_on", []))
                    if deps.issubset(completed):
                        batch.append(t["id"])
            logger.info(f"📋 Plan node: {len(batch)} tasks ready to run")
            return {"current_batch": batch}

        async def human_review_node(state: OrchestratorState) -> dict:
            """人類審核節點 (目前自動通過，可擴展為 Telegram/Dashboard 確認)"""
            batch = state.get("current_batch", [])
            logger.info(f"👤 Human Review: {len(batch)} tasks pending approval → Auto-approved")
            # TODO: 實作真實的 human approval (如 Telegram inline keyboard)
            return {"human_approved": True}

        async def execute_batch_node(state: OrchestratorState) -> dict:
            """平行執行一個批次的子任務"""
            batch_ids = state.get("current_batch", [])
            tasks = state["tasks"]
            results = dict(state.get("results", {}))

            # 找出 SubTask 物件
            batch_tasks = [t for t in tasks if t["id"] in batch_ids]

            async def run_one(task_dict: dict) -> tuple:
                sub = SubTask(**task_dict)
                # 構建上下文
                ctx = "Completed dependencies:\n"
                for dep_id in sub.depends_on:
                    if dep_id in results:
                        ctx += f"- [{dep_id}]: {results[dep_id][:300]}...\n"
                try:
                    result = await self.dispatch_task(sub, global_context=ctx)
                    return task_dict["id"], "completed", result
                except Exception:
                    return task_dict["id"], "failed", ""

            coros = [run_one(t) for t in batch_tasks]
            outcomes = await asyncio.gather(*coros)

            new_completed = []
            for tid, status, result in outcomes:
                if status == "completed":
                    results[tid] = result
                    new_completed.append(tid)
                # 更新 tasks 狀態
                for t in tasks:
                    if t["id"] == tid:
                        t["status"] = status
                        t["result"] = result

            logger.info(f"✅ Execute batch: {len(new_completed)}/{len(batch_ids)} succeeded")
            return {"results": results, "completed": new_completed, "tasks": tasks}

        def should_continue(state: OrchestratorState) -> str:
            """條件邊：判斷是否還有任務要做"""
            tasks = state.get("tasks", [])
            completed = set(state.get("completed", []))
            pending = [t for t in tasks if t["id"] not in completed and t.get("status") != "failed"]
            if pending:
                return "continue"
            return "done"

        # === Graph Wiring ===
        graph.add_node("plan", plan_node)
        graph.add_node("human_review", human_review_node)
        graph.add_node("execute", execute_batch_node)

        graph.add_edge(START, "plan")
        graph.add_edge("plan", "human_review")
        graph.add_edge("human_review", "execute")
        graph.add_conditional_edges("execute", should_continue, {
            "continue": "plan",
            "done": END,
        })

        return graph.compile()

    async def run_dag_langgraph(self, planner: Any) -> Dict[str, str]:
        """使用 LangGraph 執行完整 DAG。"""
        graph = self.build_graph(planner)

        initial_state: OrchestratorState = {
            "objective": planner.current_plan.objective,
            "tasks": [t.model_dump() for t in planner.current_plan.tasks],
            "completed": [],
            "results": {},
            "human_approved": False,
            "current_batch": [],
        }

        final_state = await graph.ainvoke(initial_state)
        return final_state.get("results", {})

    # ----------------------------------------------------------
    # Asyncio Fallback (when langgraph is not installed)
    # ----------------------------------------------------------
    async def run_dag(
        self,
        planner: Any,
        use_crewai: bool = False,
        swarm_mode: SwarmMode = SwarmMode.FLAT,
    ) -> Dict[str, str]:
        """
        主入口：優先使用 LangGraph，可選 CrewAI 流程，否則退回 asyncio fallback。
        
        Args:
            planner: TaskPlanner 實例
            use_crewai: 是否使用 CrewAI
            swarm_mode: Swarm 執行模式 (FLAT / HIERARCHICAL)
        """
        if use_crewai and CREWAI_AVAILABLE:
            logger.info("👥 Using CrewAI for DAG execution")
            return await run_crewai_dag(planner, self.engine)

        if LANGGRAPH_AVAILABLE:
            logger.info(f"🔗 Using LangGraph StateGraph (mode={swarm_mode.value}, depth={self._depth})")
            return await self.run_dag_langgraph(planner)

        logger.info("🔄 Using asyncio fallback for DAG execution")
        return await self._run_dag_asyncio(planner)

    # ----------------------------------------------------------
    # Hierarchical Swarm
    # ----------------------------------------------------------
    async def spawn_sub_swarm(
        self,
        sub_tasks: List[SubTask],
        objective: str = "",
    ) -> Dict[str, str]:
        """
        產生一個子 Swarm 來處理複雜子任務。
        
        當一個子任務很複雜時，Orchestrator 可以將它進一步分解為更小的任務，
        交給一個新的 A2ABus 實例遞迴執行。
        
        Args:
            sub_tasks: 子任務列表
            objective: 子 Swarm 的總目標
            
        Returns:
            各子任務的結果
            
        Raises:
            RecursionError: Swarm 深度超過 MAX_SWARM_DEPTH
        """
        new_depth = self._depth + 1
        if new_depth > MAX_SWARM_DEPTH:
            logger.error(
                f"🚨 Swarm 深度超過上限 ({MAX_SWARM_DEPTH})！"
                f"拒絕延伸以防無限遞迴。"
            )
            raise RecursionError(
                f"Swarm depth exceeded maximum ({MAX_SWARM_DEPTH}). "
                f"Aborting to prevent infinite recursion."
            )

        logger.info(
            f"🐝 Spawning sub-swarm (depth={new_depth}/{MAX_SWARM_DEPTH}, "
            f"tasks={len(sub_tasks)}, objective='{objective[:50]}...')"
        )

        # 建立子 A2ABus
        child_bus = A2ABus(engine=self.engine, depth=new_depth)

        # 遏輯執行子任務
        results: Dict[str, str] = {}
        for task in sub_tasks:
            try:
                result = await child_bus.dispatch_task(
                    task,
                    global_context=f"[Sub-Swarm Depth {new_depth}] Objective: {objective}",
                )
                results[task.id] = result
            except Exception as e:
                logger.error(f"❌ Sub-swarm task [{task.id}] failed: {e}")
                results[task.id] = f"Error: {e}"

        logger.info(f"✅ Sub-swarm (depth={new_depth}) completed: {len(results)} tasks")
        return results

    async def _run_dag_asyncio(self, planner: Any) -> Dict[str, str]:
        """Fallback DAG executor (pure asyncio)."""
        while True:
            runnable = planner.get_next_runnable_tasks()
            if not runnable:
                all_done = all(
                    t.status in ["completed", "failed"]
                    for t in planner.current_plan.tasks
                )
                if all_done:
                    break
                logger.error("🚨 DAG Deadlock! Unfinished tasks but none runnable.")
                break

            coros = []
            for t in runnable:
                t.status = "in_progress"
                coros.append(self._exec_single_asyncio(planner, t))

            await asyncio.gather(*coros)

        return {t.id: t.result for t in planner.current_plan.tasks if t.result}

    async def _exec_single_asyncio(self, planner: Any, task: SubTask):
        """Execute a single task in asyncio fallback mode."""
        try:
            ctx = "Completed dependencies:\n"
            for dep_id in task.depends_on:
                dep = next((t for t in planner.current_plan.tasks if t.id == dep_id), None)
                if dep and dep.result:
                    ctx += f"- [{dep_id}]: {dep.result[:300]}...\n"

            result = await self.dispatch_task(task, global_context=ctx)
            planner.update_task_status(task.id, "completed", result)
        except Exception:
            planner.update_task_status(task.id, "failed")
