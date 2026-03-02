import json
import logging
import os
from dataclasses import dataclass
from typing import Optional, Any, Dict, List

logger = logging.getLogger(__name__)

# 載入 capabilities json
CAPABILITIES_FILE = os.path.join(os.path.dirname(__file__), "model_capabilities.json")

class SmartRouter:
    """
    AgentOS v5.0 Hybrid Model Router.
    負責根據任務複雜度、網路狀態與成本限制，動態決定要使用哪顆模型。
    """
    def __init__(self, config: Any):
        self.config = config
        self.capabilities = self._load_capabilities()
        self.offline_mode = False

    def _load_capabilities(self) -> Dict[str, Any]:
        try:
            with open(CAPABILITIES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"⚠️ 無法載入 model_capabilities.json, fallback over to empty: {e}")
            return {"models": {}, "roles": {}}

    def set_offline_mode(self, offline: bool = True):
        """當 Gateway 偵測到 ConnectError 時，可強制切換為離線模式"""
        if offline and not self.offline_mode:
            logger.warning("🚨 Network disconnected! SmartRouter switching to OFFLINE MODE (Local NPU/Ollama only).")
        elif not offline and self.offline_mode:
            logger.info("📡 Network restored. SmartRouter switching back to HYBRID MODE.")
        self.offline_mode = offline

    def get_providers_dict(self) -> Dict[str, Any]:
        """建立 provider name 到 provider config 的 lookup dict"""
        return {p.name: p for p in self.config.gateway.providers}

    def determine_complexity(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> str:
        """
        基礎判定邏輯：
        - 如果工具很多 (>5) 或歷史對話很長 (> 10 turns)，視為 complex
        - 如果有程式碼關鍵字或系統提示字數極多，視為 coding / complex
        - 否則為 basic
        """
        tool_count = len(tools) if tools else 0
        turn_count = sum(1 for m in messages if m.get("role") in ["user", "assistant"])
        
        system_prompts = [m.get("content", "") for m in messages if m.get("role") == "system"]
        full_sys_text = " ".join([str(c) for c in system_prompts if isinstance(c, str)])
        
        if tool_count >= 5 or turn_count > 10:
            return "complex"
            
        if "code" in full_sys_text.lower() or "python" in full_sys_text.lower() or "developer" in full_sys_text.lower():
            return "coding"
            
        return "basic"

    def route(self, request_agent_id: str, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> tuple[str, str, Optional[str]]:
        """
        決定最終要用哪個 provider 和 model。
        Returns: (provider_name, model_name, override_base_url)
        """
        providers_dict = self.get_providers_dict()
        
        # 1. 如果在離線模式，強制使用 fallback_offline 列表中的模型 (如果可用的話)
        if self.offline_mode:
            fallback_models = self.capabilities.get("roles", {}).get("fallback_offline", [])
            for fallback_id in fallback_models:
                parts = fallback_id.split("/")
                if len(parts) == 2:
                    prov, mod = parts[0], parts[1]
                    if prov in providers_dict and providers_dict[prov].base_url: # 本地需要有 base_url 設定 (如 ollama)
                        logger.info(f"🔄 Router [OFFLINE]: Redirected request to {fallback_id}")
                        return prov, mod, providers_dict[prov].base_url
            
            # 如果沒有合適的本地 fallback，只能拿原本設定中第一個有 base_url 的硬上
            for p_name, p_config in providers_dict.items():
                if p_config.base_url:
                    first_model = p_config.models[0] if p_config.models else "llama3.2"
                    logger.info(f"🔄 Router [OFFLINE]: Redirected request to {p_name}/{first_model}")
                    return p_name, first_model, p_config.base_url
            
            # 真的沒招，丟回去原本的，等著 timeout 失敗
            logger.warning("⚠️ Router [OFFLINE]: No local provider found in config! Request might fail.")

        # 2. 如果設定檔中有指定針對這隻 agent_id 的模型，優先看看能不能用
        config_mapped = self.config.gateway.agents.get(request_agent_id)
        if config_mapped:
            parts = config_mapped.split(",") # 允許逗號分隔多個模型作為順位
            primary = parts[0].strip()
            prov_mod = primary.split("/")
            if len(prov_mod) == 2:
                prov, mod = prov_mod[0], prov_mod[1]
                logger.debug(f"🔄 Router: Using specific config for {request_agent_id} -> {primary}")
                return prov, mod, providers_dict.get(prov).base_url if prov in providers_dict else None
                
        # 3. Dynamic Routing 基於 Complexity (如果 agent_id 沒有綁定，或要求 auto)
        # 這裡為了展示概念，我們先針對 "default" 或 "auto" agent 做動態分配
        if request_agent_id in ["default", "auto"]:
            complexity = self.determine_complexity(messages, tools)
            role_map = {
                "complex": "orchestrator",
                "coding": "coder",
                "basic": "writer"
            }
            target_role = role_map.get(complexity, "writer")
            
            candidates = self.capabilities.get("roles", {}).get(target_role, [])
            for cand in candidates:
                parts = cand.split("/")
                if len(parts) == 2:
                    prov, mod = parts[0], parts[1]
                    # 檢查使用者 config 中有沒有這個 provider，且有設定 api key 或 base url
                    p_cfg = providers_dict.get(prov)
                    if p_cfg and (p_cfg.api_key or p_cfg.base_url):
                        logger.info(f"🧠 Router: Task complexity is '{complexity}'. Auto-routed to {cand}")
                        return prov, mod, p_cfg.base_url

        # 4. Fallback 給第一個設定檔裡面的合法模型
        for p_name, p_config in providers_dict.items():
            if p_config.api_key or p_config.base_url:
                if p_config.models:
                    logger.info(f"🔄 Router: Fallback to {p_name}/{p_config.models[0]}")
                    return p_name, p_config.models[0], p_config.base_url

        raise ValueError("No valid provider configurations found to match the route.")
