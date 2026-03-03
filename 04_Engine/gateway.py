"""
04_Engine — API Gateway (v5.0 SOTA — litellm)
==============================================
管理 LLM API 呼叫的完整生命週期：
  路由 → Key 注入 → 發送 → 重試 → Failover

使用 litellm 作為統一代理層，原生支援 100+ 模型 Provider。
不再需要手動構建 per-provider 的 payload 或 endpoint。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

try:
    import litellm
    litellm.drop_params = True          # 自動丟棄不支援的參數
    litellm.set_verbose = False
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False

from config_schema import AgentOSConfig, ProviderConfig
from contracts.interfaces import APICallRecord

try:
    from .router import SmartRouter
except ImportError:
    from router import SmartRouter

logger = logging.getLogger(__name__)


# ============================================================
# API Gateway (litellm-backed)
# ============================================================

class APIGateway:
    """
    API 閘道器 (v5.0 SOTA)。
    透過 litellm 統一代理所有 LLM Provider：
      OpenAI / Anthropic / Google / Ollama / DeepSeek / Groq / Mistral / Together / ...
    """

    def __init__(self, config: AgentOSConfig):
        self.config = config
        self._providers: dict[str, ProviderConfig] = {}
        self._call_history: list[APICallRecord] = []

        for p in config.gateway.providers:
            self._providers[p.name] = p
            # 將 API key 注入 litellm 環境 (litellm 會自動讀取)
            self._register_provider_keys(p)

        self._router = SmartRouter(config)

        backend = "litellm" if LITELLM_AVAILABLE else "httpx-fallback"
        logger.info(f"🌐 API Gateway 啟動: {len(self._providers)} providers, backend={backend}, SmartRouter 就緒")

    @staticmethod
    def _register_provider_keys(p: ProviderConfig) -> None:
        """將 provider 的 API key 注入 litellm 的環境變數映射。"""
        if not LITELLM_AVAILABLE or not p.api_key:
            return
        import os
        key_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GEMINI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "groq": "GROQ_API_KEY",
            "mistral": "MISTRAL_API_KEY",
            "together": "TOGETHERAI_API_KEY",
        }
        env_var = key_map.get(p.name)
        if env_var:
            os.environ[env_var] = p.api_key

    def resolve_model(
        self,
        agent_id: str = "default",
        messages: list[dict] | None = None,
        tools: list[dict] | None = None,
    ) -> tuple[ProviderConfig, str]:
        """由 SmartRouter 決定最佳 Provider + Model。"""
        if messages is None:
            messages = []

        provider_name, model, override_url = self._router.route(agent_id, messages, tools)
        base_provider = self._providers.get(provider_name, ProviderConfig(name=provider_name))

        call_provider = ProviderConfig(
            name=base_provider.name,
            api_key=base_provider.api_key,
            base_url=override_url or base_provider.base_url,
            models=base_provider.models,
        )
        return call_provider, model

    # ----------------------------------------------------------
    # litellm model identifier 轉換
    # ----------------------------------------------------------
    @staticmethod
    def _to_litellm_model(provider_name: str, model: str) -> str:
        """
        將 AgentOS 的 provider/model 轉換為 litellm 認得的 model identifier。
        litellm 格式：provider/model (如 'anthropic/claude-3.5-sonnet')
        Ollama 格式：'ollama/llama3'
        OpenAI 格式：直接用 model name (如 'gpt-4o')
        """
        prefix_map = {
            "openai": "",               # litellm 原生支援
            "anthropic": "anthropic/",
            "google": "gemini/",
            "ollama": "ollama/",
            "deepseek": "deepseek/",
            "groq": "groq/",
            "mistral": "mistral/",
            "together": "together_ai/",
        }
        prefix = prefix_map.get(provider_name, f"{provider_name}/")
        return f"{prefix}{model}"

    # ----------------------------------------------------------
    # 核心呼叫
    # ----------------------------------------------------------
    async def call(
        self,
        messages: list[dict],
        agent_id: str = "default",
        tools: Optional[list[dict]] = None,
        stream: bool = False,
        temperature: float = 0.7,
        **kwargs
    ) -> dict[str, Any]:
        """
        發送 LLM API 請求，含自動重試與離線 failover。
        優先使用 litellm；若 litellm 不可用則退回 httpx fallback。
        """
        retry_cfg = self.config.engine.retry
        last_error: Optional[Exception] = None

        for attempt in range(retry_cfg.max_attempts):
            provider, model = self.resolve_model(agent_id, messages, tools)

            try:
                if LITELLM_AVAILABLE:
                    result = await self._call_via_litellm(
                        provider=provider, model=model,
                        messages=messages, tools=tools,
                        stream=stream, temperature=temperature,
                        **kwargs
                    )
                else:
                    result = await self._call_via_httpx(
                        provider=provider, model=model,
                        messages=messages, tools=tools,
                        temperature=temperature,
                        **kwargs
                    )
                return result

            except APIError as e:
                last_error = e
                if e.status_code == 599:
                    logger.warning("🚨 Gateway 捕獲網路斷線 (599)，SmartRouter 切換離線模式！")
                    self._router.set_offline_mode(True)
                    continue

                if e.status_code in retry_cfg.retryable_codes and attempt < retry_cfg.max_attempts - 1:
                    wait = retry_cfg.backoff_multiplier ** attempt
                    logger.warning(f"⚠️ API 錯誤 {e.status_code}，{wait}s 後重試 (attempt {attempt + 1})")
                    await asyncio.sleep(wait)
                else:
                    raise

        raise last_error or APIError(500, "Max retries exceeded")

    # ----------------------------------------------------------
    # litellm backend
    # ----------------------------------------------------------
    async def _call_via_litellm(
        self,
        provider: ProviderConfig,
        model: str,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        stream: bool = False,
        temperature: float = 0.7,
        **kwargs
    ) -> dict[str, Any]:
        """使用 litellm.acompletion() 進行 LLM 呼叫。"""
        litellm_model = self._to_litellm_model(provider.name, model)

        call_kwargs: dict[str, Any] = {
            "model": litellm_model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }

        # Ollama 或其他自建端點需要 base_url
        if provider.base_url:
            call_kwargs["api_base"] = provider.base_url

        # 如果有 API key 直接傳入 (覆蓋環境變數)
        if provider.api_key:
            call_kwargs["api_key"] = provider.api_key

        # Tool calling
        if tools:
            call_kwargs["tools"] = [{"type": "function", "function": t} for t in tools]
            # litellm 預設會自動選擇 tool_choice = "auto"

        # 合併額外的 kwargs
        call_kwargs.update(kwargs)

        start = time.time()
        try:
            response = await litellm.acompletion(**call_kwargs)
        except Exception as e:
            error_str = str(e)
            if "connect" in error_str.lower() or "timeout" in error_str.lower():
                raise APIError(599, f"Network connection failed: {error_str}")
            raise APIError(500, f"litellm error: {error_str}")

        elapsed_ms = int((time.time() - start) * 1000)

        # litellm 回傳 ModelResponse，轉為 dict
        result = response.model_dump() if hasattr(response, "model_dump") else dict(response)

        # 記錄呼叫
        usage = result.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        record = APICallRecord(
            model=model,
            provider=provider.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            agent_id="default",
        )
        self._call_history.append(record)

        logger.info(
            f"✅ [{provider.name}/{model}] via litellm ({elapsed_ms}ms, "
            f"in:{input_tokens} out:{output_tokens})"
        )
        return result

    # ----------------------------------------------------------
    # httpx fallback (當 litellm 未安裝時)
    # ----------------------------------------------------------
    async def _call_via_httpx(
        self,
        provider: ProviderConfig,
        model: str,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
        **kwargs
    ) -> dict[str, Any]:
        """Fallback: 用 httpx 直接打 OpenAI-compatible endpoint。"""
        import httpx

        base = provider.base_url or "https://api.openai.com"
        endpoint = f"{base.rstrip('/')}/v1/chat/completions"

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]
        
        # 合併額外的 kwargs
        payload.update(kwargs)

        headers: dict[str, str] = {"content-type": "application/json"}
        if provider.api_key:
            headers["authorization"] = f"Bearer {provider.api_key}"

        start = time.time()
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                resp = await client.post(endpoint, json=payload, headers=headers)
                resp.raise_for_status()
                result = resp.json()
            except httpx.ConnectError as e:
                raise APIError(599, f"Network connection failed: {e}")
            except httpx.HTTPStatusError as e:
                raise APIError(e.response.status_code, f"API Error: {e.response.text}")

        elapsed_ms = int((time.time() - start) * 1000)

        input_tokens = result.get("usage", {}).get("prompt_tokens", 0)
        output_tokens = result.get("usage", {}).get("completion_tokens", 0)

        record = APICallRecord(
            model=model, provider=provider.name,
            input_tokens=input_tokens, output_tokens=output_tokens,
            agent_id="default",
        )
        self._call_history.append(record)

        logger.info(f"✅ [{provider.name}/{model}] via httpx ({elapsed_ms}ms, in:{input_tokens} out:{output_tokens})")
        return result

    def get_call_history(self) -> list[APICallRecord]:
        """取得所有 API 呼叫紀錄 (供 Cost Guard 使用)"""
        return self._call_history


class APIError(Exception):
    """API 呼叫錯誤"""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"[{status_code}] {message}")
