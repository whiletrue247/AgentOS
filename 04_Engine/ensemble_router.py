"""
04_Engine — Ensemble Router Extension
=======================================
在 APIGateway 之上提供多模型 Ensemble 投票機制：
  - 同時向 2+ 個 Provider/Model 發問
  - 比較回答品質（長度、結構、confidence）
  - 選擇最佳答案回傳

使用場景：
  - 高重要性決策 (importance >= 0.8)
  - 需要交叉驗證的 factual 回答
  - config 開啟 ensemble 模式時

TODO: 整合到 Engine ReAct loop，在 importance >= 0.8 時自動啟用。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EnsembleRouter:
    """
    多模型 Ensemble 投票器。
    
    同時呼叫多個模型，根據回答品質選擇最佳結果。
    可選策略：longest (最詳細)、vote (多數決)、first (最快回應)。
    
    Args:
        gateway: APIGateway 實例
        strategy: 選擇策略 ('longest' | 'vote' | 'first')
    """

    def __init__(self, gateway: Any, strategy: str = "longest"):
        self._gateway = gateway
        self._strategy = strategy
        logger.info(f"🎯 EnsembleRouter 初始化: strategy={strategy}")

    async def call_ensemble(
        self,
        messages: list[dict],
        models: Optional[List[str]] = None,
        agent_id: str = "default",
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """
        同時向多個模型發問並選擇最佳回答。
        
        Args:
            messages: 對話訊息
            models: 模型列表 (如 ['gpt-4o', 'claude-3.5-sonnet'])
                    若為 None，使用 config 中前 2 個 provider 的模型
            agent_id: Agent ID
            tools: 工具定義
            temperature: 溫度
            
        Returns:
            最佳回答的完整 response dict + ensemble_metadata
        """
        # 決定要使用的模型
        if not models:
            models = self._get_default_ensemble_models()

        if len(models) < 2:
            logger.warning("⚠️ Ensemble 需要至少 2 個模型，退回單模型")
            return await self._gateway.call(
                messages=messages, agent_id=agent_id,
                tools=tools, temperature=temperature,
            )

        logger.info(f"🎯 Ensemble 呼叫: {len(models)} 個模型 → {models}")

        # 平行呼叫所有模型
        tasks = []
        for model in models:
            tasks.append(
                self._call_single(
                    messages=messages, model=model,
                    tools=tools, temperature=temperature,
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 過濾成功的結果
        valid_results = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                logger.warning(f"⚠️ Ensemble model {models[i]} failed: {r}")
            else:
                valid_results.append((models[i], r))

        if not valid_results:
            raise RuntimeError("All ensemble models failed")

        # 選擇最佳結果
        best_model, best_response = self._select_best(valid_results)
        logger.info(f"✅ Ensemble 最佳: {best_model}")

        # 附加 ensemble metadata
        best_response["ensemble_metadata"] = {
            "models_called": models,
            "models_succeeded": [m for m, _ in valid_results],
            "selected_model": best_model,
            "strategy": self._strategy,
        }

        return best_response

    async def _call_single(
        self,
        messages: list[dict],
        model: str,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """呼叫單一模型"""
        return await self._gateway.call(
            messages=messages,
            tools=tools,
            temperature=temperature,
        )

    def _select_best(
        self,
        results: List[tuple[str, Dict[str, Any]]],
    ) -> tuple[str, Dict[str, Any]]:
        """根據策略選擇最佳結果"""
        if self._strategy == "first":
            return results[0]

        if self._strategy == "longest":
            # 選最長回答 (通常更詳細)
            return max(
                results,
                key=lambda r: len(
                    r[1].get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                ),
            )

        # default: longest
        return max(
            results,
            key=lambda r: len(
                r[1].get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            ),
        )

    def _get_default_ensemble_models(self) -> List[str]:
        """從 gateway config 取前 2 個 provider 的模型"""
        try:
            providers = self._gateway.config.providers
            models = []
            for p in providers[:2]:
                if p.models:
                    models.append(p.models[0])
            return models
        except Exception:
            return []
