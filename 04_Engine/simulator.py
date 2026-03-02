"""
04_Engine — Agent Simulator (v5.0 SOTA)
=========================================
允許人類在按下「執行」前，要求 Agent 預判並模擬跑 N 步。
使用真實的 LLM 推理 (dry-run 模式) 而非假字串。

核心能力：
  - simulate_n_steps(): 呼叫 LLM 進行 CoT 預測，回傳可能的行動軌跡
  - Risk scoring: 每步自動評估風險等級
  - Token estimation: 預估整個任務的 Token 消耗
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class AgentSimulator:
    """
    Agent 模擬器 (v5.0 SOTA)。
    使用 LLM 做真實的 dry-run 推理，而非返回假字串。
    """

    def __init__(self, engine: Any):
        self.engine = engine
        logger.info("🔮 AgentSimulator 初始化完成")

    async def simulate_n_steps(
        self,
        task_objective: str,
        steps: int = 10,
        available_tools: List[str] | None = None,
    ) -> List[Dict[str, Any]]:
        """
        模擬未來 N 步的行動軌跡。
        透過 LLM CoT 推理預測 Agent 可能採取的工具呼叫和結果。
        """
        logger.info(f"🕹️ 模擬任務: '{task_objective}' (最多 {steps} 步)")

        tools_str = ", ".join(available_tools) if available_tools else "search_web, execute_code, read_file, write_file"

        prompt = f"""You are an Agent Simulator. Given a task objective, predict the step-by-step execution plan.

OBJECTIVE: {task_objective}
AVAILABLE TOOLS: {tools_str}
MAX STEPS: {steps}

For each step, output a JSON object with:
- "step": step number
- "thought": what the agent would think (Chain of Thought)
- "proposed_action": the tool call the agent would make (tool_name + arguments)
- "expected_observation": what the tool would likely return
- "risk_level": "low", "medium", or "high"
- "estimated_tokens": rough token cost for this step

IMPORTANT:
- Be realistic about what each tool would return
- Flag any destructive operations (file deletion, system changes) as "high" risk
- Stop early if the task would be complete before {steps} steps

Return ONLY a JSON array of step objects. No other text."""

        messages = [
            {"role": "system", "content": "You are a precise simulation engine that predicts agent behavior."},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self.engine.gateway.call(
                messages=messages,
                agent_id="orchestrator",
                temperature=0.3,
            )
            raw = response["choices"][0]["message"]["content"]
            trajectory = self._parse_trajectory(raw)

            # 後處理：額外風險掃描
            for step in trajectory:
                step["risk_level"] = self._assess_risk(step)

            total_tokens = sum(s.get("estimated_tokens", 500) for s in trajectory)
            high_risk_count = sum(1 for s in trajectory if s["risk_level"] == "high")

            logger.info(
                f"🏁 模擬完成: {len(trajectory)} 步, "
                f"預估 {total_tokens} tokens, "
                f"{high_risk_count} 高風險步驟"
            )
            return trajectory

        except Exception as e:
            logger.error(f"❌ 模擬失敗: {e}")
            return [{
                "step": 1,
                "thought": f"Simulation failed: {e}",
                "proposed_action": "none",
                "expected_observation": "error",
                "risk_level": "unknown",
                "estimated_tokens": 0,
            }]

    def get_summary(self, trajectory: List[Dict[str, Any]]) -> Dict[str, Any]:
        """從模擬軌跡產生摘要統計。"""
        total_steps = len(trajectory)
        total_tokens = sum(s.get("estimated_tokens", 500) for s in trajectory)
        high_risk = [s for s in trajectory if s.get("risk_level") == "high"]

        return {
            "total_steps": total_steps,
            "estimated_tokens": total_tokens,
            "estimated_cost_m": round(total_tokens / 1_000_000, 4),
            "high_risk_steps": len(high_risk),
            "high_risk_details": [
                {"step": s["step"], "action": s.get("proposed_action", "")}
                for s in high_risk
            ],
            "recommendation": "proceed" if not high_risk else "review_required",
        }

    # ----------------------------------------------------------
    # 風險評估
    # ----------------------------------------------------------
    @staticmethod
    def _assess_risk(step: Dict[str, Any]) -> str:
        """基於行動內容進行額外風險判定。"""
        action = str(step.get("proposed_action", "")).lower()

        high_risk_patterns = [
            "rm ", "delete", "drop ", "truncate", "format",
            "sudo", "chmod 777", "curl | bash", "eval(",
            "os.system", "subprocess.run", "exec(",
        ]
        medium_risk_patterns = [
            "write_file", "modify", "update", "install",
            "pip install", "npm install", "apt ", "brew ",
        ]

        for pattern in high_risk_patterns:
            if pattern in action:
                return "high"
        for pattern in medium_risk_patterns:
            if pattern in action:
                return "medium"

        # 保留 LLM 原始判定
        return step.get("risk_level", "low")

    @staticmethod
    def _parse_trajectory(raw: str) -> List[Dict[str, Any]]:
        """解析 LLM 回傳的模擬軌跡。"""
        import json
        text = raw.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
        return []
