"""
04_Engine — Smart Model Router (v5.1 — Dynamic Scoring)
============================================
根據以下維度動態路由 LLM 請求：
  1. 任務複雜度 (tool count, turn count, system prompt keywords)
  2. 網路狀態 (離線 → 強制本地)
  3. 硬體加速器 (NPU/GPU 偵測 → 優先本地推論)
  4. 成本感知 (litellm model_cost → 超支自動降級)
  5. 使用者綁定 (config.yaml agents 映射)
  6. 動態評分 (Sprint 1 新增: 歷史成功率 + 延遲 + 價格 啟發式評分)
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List

__all__ = ["SmartRouter"]

logger = logging.getLogger(__name__)

CAPABILITIES_FILE = os.path.join(os.path.dirname(__file__), "model_capabilities.json")

# 嘗試載入 litellm 成本資料
try:
    from litellm import model_cost as LITELLM_MODEL_COST
except ImportError:
    LITELLM_MODEL_COST = {}

# 嘗試載入 NPU 偵測器
try:
    from .npu_detector import NPUDetector
except ImportError:
    try:
        from npu_detector import NPUDetector
    except ImportError:
        NPUDetector = None


@dataclass
class ModelStats:
    """模型歷史表現統計 (用於動態路由評分)"""
    model: str = ""
    total_calls: int = 0
    success_count: int = 0
    total_latency_ms: float = 0.0
    recent_latencies: List[float] = field(default_factory=list)


class SmartRouter:
    """
    AgentOS v5.0 Hybrid Model Router.
    負責根據任務複雜度、網路狀態、硬體與成本限制，動態決定要使用哪顆模型。
    """

    def __init__(self, config: Any):
        self.config = config
        self.capabilities = self._load_capabilities()
        self.offline_mode = False

        # NPU/GPU 硬體偵測
        self.hw_profile = None
        if NPUDetector:
            try:
                self.hw_profile = NPUDetector.detect()
                logger.info(f"🔧 Router NPU backend: {self.hw_profile.recommended_local_backend}")
            except Exception as e:
                logger.warning(f"⚠️ NPU detection failed: {e}")

        # 成本追蹤 (累計 session input/output tokens)
        self._session_cost_usd = 0.0

        # 動態評分器：追蹤每個模型的歷史表現 (Sprint 1 新增)
        self._model_stats: Dict[str, ModelStats] = {}

    def _load_capabilities(self) -> Dict[str, Any]:
        try:
            with open(CAPABILITIES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"⚠️ 無法載入 model_capabilities.json: {e}")
            return {"models": {}, "roles": {}}

    def set_offline_mode(self, offline: bool = True):
        """當 Gateway 偵測到 ConnectError 時，強制切換為離線模式"""
        if offline and not self.offline_mode:
            logger.warning("🚨 Network disconnected! SmartRouter → OFFLINE MODE (Local only).")
        elif not offline and self.offline_mode:
            logger.info("📡 Network restored. SmartRouter → HYBRID MODE.")
        self.offline_mode = offline

    def get_providers_dict(self) -> Dict[str, Any]:
        return {p.name: p for p in self.config.gateway.providers}

    # ----------------------------------------------------------
    # 複雜度判定
    # ----------------------------------------------------------
    def determine_complexity(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        tool_count = len(tools) if tools else 0
        turn_count = sum(1 for m in messages if m.get("role") in ["user", "assistant"])

        system_prompts = [m.get("content", "") for m in messages if m.get("role") == "system"]
        full_sys_text = " ".join([str(c) for c in system_prompts if isinstance(c, str)])

        if tool_count >= 5 or turn_count > 10:
            return "complex"
        if any(kw in full_sys_text.lower() for kw in ["code", "python", "developer", "typescript", "rust"]):
            return "coding"
        return "basic"

    # ----------------------------------------------------------
    # 成本感知降級
    # ----------------------------------------------------------
    def estimate_cost(self, provider_name: str, model: str) -> float:
        """
        使用 litellm model_cost 資料估算每次呼叫成本 (USD per 1K tokens)。
        若無資料則回傳 0 (不限制)。
        """
        if not LITELLM_MODEL_COST:
            return 0.0

        candidates = [
            model,
            f"{provider_name}/{model}",
            model.replace(f"{provider_name}/", "")
        ]
        for key in candidates:
            if key in LITELLM_MODEL_COST:
                info = LITELLM_MODEL_COST[key]
                return info.get("input_cost_per_token", 0) * 1000
        return 0.0

    def get_cheaper_alternative(self, current_model: str) -> Optional[str]:
        """如果預算超支，嘗試找一個更便宜的模型。"""
        budget_limit = getattr(self.config, "budget", None)
        if not budget_limit:
            return None

        daily_limit = getattr(budget_limit, "daily_limit_m", 1.0)
        # 簡易判定是否接近上限 (> 80%)
        if self._session_cost_usd < daily_limit * 0.8:
            return None

        # 從 capabilities 中找最便宜的 cloud 模型候選
        cheap_models = self.capabilities.get("roles", {}).get("writer", [])
        if cheap_models:
            logger.warning(f"💸 Budget approaching limit! Downgrading '{current_model}' to '{cheap_models[0]}'")
            return cheap_models[0]
        return None

    def record_cost(self, input_tokens: int, output_tokens: int, model: str):
        """由 Gateway 呼叫，記錄本次 API 的消耗。支援 litellm response.usage 整合"""
        if not LITELLM_MODEL_COST:
            return
            
        cost = 0.0
        try:
            # 這裡簡化為字典查找，因為 model name 有可能需要 mapping
            model_key = model
            for k in LITELLM_MODEL_COST.keys():
                if model.endswith(k) or k.endswith(model):
                    model_key = k
                    break
            
            info = LITELLM_MODEL_COST.get(model_key, {})
            cost = (
                input_tokens * info.get("input_cost_per_token", 0)
                + output_tokens * info.get("output_cost_per_token", 0)
            )
        except Exception as e:
            logger.debug(f"Litellm cost tracking failed: {e}")
            
        if cost > 0:
            self._session_cost_usd += cost
            logger.debug(f"💰 Session cost updated +${cost:.4f} (Total: ${self._session_cost_usd:.4f})")

    # ----------------------------------------------------------
    # 動態評分器 (Sprint 1 新增)
    # ----------------------------------------------------------

    def record_outcome(self, model: str, success: bool, latency_ms: float) -> None:
        """
        記錄模型呼叫結果，用於動態評分。
        由 Gateway 在每次 API 呼叫後調用。
        """
        if model not in self._model_stats:
            self._model_stats[model] = ModelStats(model=model)
        stats = self._model_stats[model]
        stats.total_calls += 1
        if success:
            stats.success_count += 1
        stats.total_latency_ms += latency_ms
        # 保留最近 20 次的延遲記錄
        stats.recent_latencies.append(latency_ms)
        if len(stats.recent_latencies) > 20:
            stats.recent_latencies.pop(0)

    def _score_model(self, provider: str, model: str, estimated_tokens: int = 500) -> float:
        """
        啟發式評分：結合歷史成功率、延遲和價格計算最優模型。
        分數越高越好 (0.0 ~ 1.0)。

        評分公式：
          score = w_success * success_rate
                + w_speed * speed_score
                + w_cost * cost_score

        權重: 成功率(0.4) + 速度(0.3) + 價格(0.3)
        """
        key = f"{provider}/{model}"
        stats = self._model_stats.get(key)

        # 新模型（無歷史資料）→ 給予中等分數以鼓勵探索
        if not stats or stats.total_calls < 3:
            return 0.6

        # 1. 成功率分數 (0.0 ~ 1.0)
        success_rate = stats.success_count / stats.total_calls

        # 2. 速度分數 (avg_latency 越低越好，以 5000ms 為基準)
        avg_latency = stats.total_latency_ms / stats.total_calls
        speed_score = max(0.0, 1.0 - (avg_latency / 5000.0))

        # 3. 價格分數 (越便宜越好)
        cost_per_1k = self.estimate_cost(provider, model)
        if cost_per_1k <= 0:
            cost_score = 0.5  # 無價格資料→中等
        else:
            # 以 $0.03/1K tokens (GPT-4o 等級) 為基準
            cost_score = max(0.0, 1.0 - (cost_per_1k / 0.03))

        final_score = 0.4 * success_rate + 0.3 * speed_score + 0.3 * cost_score
        logger.debug(
            f"🎯 ModelScore [{key}]: success={success_rate:.2f} speed={speed_score:.2f} "
            f"cost={cost_score:.2f} → final={final_score:.3f}"
        )
        return final_score

    def get_model_stats(self) -> Dict[str, dict]:
        """取得所有模型的歷史表現統計（供 Dashboard 使用）"""
        result = {}
        for key, stats in self._model_stats.items():
            result[key] = {
                "total_calls": stats.total_calls,
                "success_rate": stats.success_count / stats.total_calls if stats.total_calls > 0 else 0,
                "avg_latency_ms": stats.total_latency_ms / stats.total_calls if stats.total_calls > 0 else 0,
                "recent_latencies": stats.recent_latencies[-5:],
            }
        return result

    # ----------------------------------------------------------
    # 主路由邏輯
    # ----------------------------------------------------------
    def route(
        self,
        request_agent_id: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> tuple[str, str, Optional[str]]:
        """
        決定最終要用哪個 provider 和 model。
        Returns: (provider_name, model_name, override_base_url)
        """
        providers_dict = self.get_providers_dict()

        # ============ 1. OFFLINE MODE ============
        if self.offline_mode:
            return self._route_offline(providers_dict)

        # ============ 2. COST DOWNGRADE CHECK ============
        cheaper = self.get_cheaper_alternative("")
        if cheaper:
            parts = cheaper.split("/")
            if len(parts) == 2:
                prov, mod = parts
                p_cfg = providers_dict.get(prov)
                if p_cfg and (p_cfg.api_key or p_cfg.base_url):
                    return prov, mod, p_cfg.base_url

        # ============ 3. CONFIG BINDING ============
        config_mapped = self.config.gateway.agents.get(request_agent_id)
        if config_mapped:
            parts = config_mapped.split(",")
            primary = parts[0].strip()
            prov_mod = primary.split("/")
            if len(prov_mod) == 2:
                prov, mod = prov_mod
                logger.debug(f"🔄 Router: Config binding {request_agent_id} → {primary}")
                return prov, mod, providers_dict.get(prov, type("", (), {"base_url": None})).base_url

        # ============ 4. NPU-AWARE LOCAL PREFERENCE ============
        if self.hw_profile and self.hw_profile.recommended_local_backend != "cpu":
            # 如果有 GPU/NPU，且 Ollama 可用，優先用本地跑 basic 任務
            complexity = self.determine_complexity(messages, tools)
            if complexity == "basic":
                for p_name, p_cfg in providers_dict.items():
                    if p_cfg.base_url and p_name in ["ollama", "lmstudio"]:
                        first_model = p_cfg.models[0] if p_cfg.models else "llama3.2"
                        logger.info(
                            f"🧠 Router: NPU ({self.hw_profile.recommended_local_backend}) available + basic task "
                            f"→ local {p_name}/{first_model}"
                        )
                        return p_name, first_model, p_cfg.base_url

        # ============ 5. DYNAMIC SCORING ROUTE (Sprint 1 新增) ============
        if request_agent_id in ["default", "auto"]:
            complexity = self.determine_complexity(messages, tools)
            role_map = {"complex": "orchestrator", "coding": "coder", "basic": "writer"}
            target_role = role_map.get(complexity, "writer")

            # 估算 token 數量 (用於 cost scoring)
            estimated_tokens = sum(
                len(str(m.get("content", ""))) // 4
                for m in messages
            )

            candidates = self.capabilities.get("roles", {}).get(target_role, [])
            scored_candidates: List[tuple[float, str]] = []
            for cand in candidates:
                parts = cand.split("/")
                if len(parts) == 2:
                    prov, mod = parts
                    p_cfg = providers_dict.get(prov)
                    if p_cfg and (p_cfg.api_key or p_cfg.base_url):
                        score = self._score_model(prov, mod, estimated_tokens)
                        scored_candidates.append((score, cand))

            # 按分數降序排列，選擇最優模型
            if scored_candidates:
                scored_candidates.sort(key=lambda x: x[0], reverse=True)
                best_score, best_cand = scored_candidates[0]
                prov, mod = best_cand.split("/")
                p_cfg = providers_dict.get(prov)
                logger.info(
                    f"🧠 Router: complexity='{complexity}' → {best_cand} "
                    f"(score={best_score:.3f}, {len(scored_candidates)} candidates)"
                )
                return prov, mod, p_cfg.base_url if p_cfg else None

        # ============ 6. FALLBACK ============
        for p_name, p_config in providers_dict.items():
            if p_config.api_key or p_config.base_url:
                if p_config.models:
                    logger.info(f"🔄 Router: Fallback to {p_name}/{p_config.models[0]}")
                    return p_name, p_config.models[0], p_config.base_url

        raise ValueError("No valid provider found in config.")

    def _route_offline(self, providers_dict: Dict[str, Any]) -> tuple[str, str, Optional[str]]:
        """離線模式路由：僅使用本地端點 (Ollama, LMStudio 等)"""
        fallback_models = self.capabilities.get("roles", {}).get("fallback_offline", [])
        for fallback_id in fallback_models:
            parts = fallback_id.split("/")
            if len(parts) == 2:
                prov, mod = parts
                if prov in providers_dict and providers_dict[prov].base_url:
                    logger.info(f"🔄 Router [OFFLINE]: → {fallback_id}")
                    return prov, mod, providers_dict[prov].base_url

        for p_name, p_config in providers_dict.items():
            if p_config.base_url:
                first_model = p_config.models[0] if p_config.models else "llama3.2"
                logger.info(f"🔄 Router [OFFLINE]: → {p_name}/{first_model}")
                return p_name, first_model, p_config.base_url

        logger.warning("⚠️ Router [OFFLINE]: No local provider found!")
        raise ValueError("No local provider available for offline mode.")
