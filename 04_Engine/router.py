"""
04_Engine — Smart Model Router (v5.0 SOTA)
============================================
根據以下維度動態路由 LLM 請求：
  1. 任務複雜度 (tool count, turn count, system prompt keywords)
  2. 網路狀態 (離線 → 強制本地)
  3. 硬體加速器 (NPU/GPU 偵測 → 優先本地推論)
  4. 成本感知 (litellm model_cost → 超支自動降級)
  5. 使用者綁定 (config.yaml agents 映射)
"""

import json
import logging
import os
from typing import Optional, Any, Dict, List

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

        # litellm model key 格式 (嘗試多種組合)
        candidates = [
            model,
            f"{provider_name}/{model}",
        ]
        for key in candidates:
            if key in LITELLM_MODEL_COST:
                info = LITELLM_MODEL_COST[key]
                # 取 input_cost_per_token 作為主要指標
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
            logger.warning(f"💸 Budget approaching limit! Downgrading to {cheap_models[0]}")
            return cheap_models[0]
        return None

    def record_cost(self, input_tokens: int, output_tokens: int, model: str):
        """由 Gateway 呼叫，記錄本次 API 的消耗。"""
        if not LITELLM_MODEL_COST:
            return
        info = LITELLM_MODEL_COST.get(model, {})
        cost = (
            input_tokens * info.get("input_cost_per_token", 0)
            + output_tokens * info.get("output_cost_per_token", 0)
        )
        self._session_cost_usd += cost

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

        # ============ 5. DYNAMIC COMPLEXITY ROUTING ============
        if request_agent_id in ["default", "auto"]:
            complexity = self.determine_complexity(messages, tools)
            role_map = {"complex": "orchestrator", "coding": "coder", "basic": "writer"}
            target_role = role_map.get(complexity, "writer")

            candidates = self.capabilities.get("roles", {}).get(target_role, [])
            for cand in candidates:
                parts = cand.split("/")
                if len(parts) == 2:
                    prov, mod = parts
                    p_cfg = providers_dict.get(prov)
                    if p_cfg and (p_cfg.api_key or p_cfg.base_url):
                        logger.info(f"🧠 Router: complexity='{complexity}' → {cand}")
                        return prov, mod, p_cfg.base_url

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
