"""
04_Engine — API Gateway
=======================
管理 LLM API 呼叫的完整生命週期：
  路由 → Key 注入 → 發送 → 重試 → Failover

支援多 Provider (OpenAI, Anthropic, Google, Ollama)。
Agent-to-Model 路由由 config.yaml 的 gateway.agents 決定。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator, Optional

from config_schema import AgentOSConfig, ProviderConfig
from contracts.interfaces import APICallRecord

logger = logging.getLogger(__name__)


# ============================================================
# Model Adapter — 統一不同 Provider 的 API 格式
# ============================================================

class ModelAdapter:
    """
    將 AgentOS 的統一訊息格式轉換為各 Provider 的原生格式。
    目前以 OpenAI Chat Completions 格式為標準，其他 Provider 做適配。
    """

    @staticmethod
    def build_request(
        provider_name: str,
        model: str,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        stream: bool = True,
        temperature: float = 0.7,
    ) -> dict:
        """構建給 httpx/aiohttp 的請求 payload"""

        # OpenAI 相容格式 (OpenAI, Ollama, DeepSeek, Groq 都用這個)
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }

        if tools:
            payload["tools"] = [
                {"type": "function", "function": t} for t in tools
            ]

        # Anthropic 需要把 system message 提出來
        if provider_name == "anthropic":
            system_msgs = [m for m in messages if m.get("role") == "system"]
            non_system = [m for m in messages if m.get("role") != "system"]
            payload["messages"] = non_system
            if system_msgs:
                payload["system"] = "\n".join(m["content"] for m in system_msgs)
            payload["max_tokens"] = 4096  # Anthropic 必填

        # Google Gemini 用不同的欄位名
        if provider_name == "google":
            payload["contents"] = [
                {"role": m.get("role", "user"), "parts": [{"text": m.get("content", "")}]}
                for m in messages if m.get("role") != "system"
            ]
            system_msgs = [m for m in messages if m.get("role") == "system"]
            if system_msgs:
                payload["systemInstruction"] = {
                    "parts": [{"text": "\n".join(m["content"] for m in system_msgs)}]
                }
            # 移除 OpenAI 格式的欄位
            payload.pop("messages", None)
            payload.pop("model", None)

        return payload

    @staticmethod
    def get_endpoint(provider: ProviderConfig, model: str) -> str:
        """取得 API endpoint URL"""
        if provider.base_url:
            return f"{provider.base_url.rstrip('/')}/v1/chat/completions"

        endpoints = {
            "openai": "https://api.openai.com/v1/chat/completions",
            "anthropic": "https://api.anthropic.com/v1/messages",
            "google": f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent",
            "deepseek": "https://api.deepseek.com/v1/chat/completions",
            "groq": "https://api.groq.com/openai/v1/chat/completions",
        }
        return endpoints.get(provider.name, endpoints["openai"])

    @staticmethod
    def get_headers(provider: ProviderConfig) -> dict[str, str]:
        """取得 API 認證 Headers"""
        if provider.name == "anthropic":
            return {
                "x-api-key": provider.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
        if provider.name == "google":
            return {
                "content-type": "application/json",
                # Google 用 query param 傳 key，不用 header
            }
        # OpenAI 相容 (OpenAI, Ollama, DeepSeek, Groq)
        headers = {"content-type": "application/json"}
        if provider.api_key:
            headers["authorization"] = f"Bearer {provider.api_key}"
        return headers


# ============================================================
# API Gateway
# ============================================================

class APIGateway:
    """
    API 閘道器。
    負責路由 Agent 的請求到正確的 Provider + Model。
    """

    def __init__(self, config: AgentOSConfig):
        self.config = config
        self._providers: dict[str, ProviderConfig] = {}
        self._call_history: list[APICallRecord] = []

        # 建立 provider name → config 的映射
        for p in config.gateway.providers:
            self._providers[p.name] = p

        logger.info(f"🌐 API Gateway 啟動: {len(self._providers)} providers 可用")

    def resolve_model(self, agent_id: str = "default") -> tuple[ProviderConfig, str]:
        """
        根據 agent_id 解析出對應的 Provider 和 Model。
        config.yaml 格式: agents.default = "openai/gpt-4o"
        """
        route = self.config.gateway.agents.get(agent_id, self.config.gateway.agents.get("default", "openai/gpt-4o"))

        if "/" in route:
            provider_name, model = route.split("/", 1)
        else:
            provider_name = "openai"
            model = route

        provider = self._providers.get(provider_name)
        if not provider:
            # Failover: 用第一個有 key 的 provider
            for p in self._providers.values():
                if p.api_key or p.base_url:
                    logger.warning(f"⚠️ Provider '{provider_name}' 不存在，failover 到 '{p.name}'")
                    return p, model
            # 全部沒 key，回傳空的
            return ProviderConfig(name=provider_name), model

        return provider, model

    async def call(
        self,
        messages: list[dict],
        agent_id: str = "default",
        tools: Optional[list[dict]] = None,
        stream: bool = True,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """
        發送 API 請求 (非串流模式，等待完整回應)。
        含自動重試邏輯。
        """
        provider, model = self.resolve_model(agent_id)
        retry_cfg = self.config.engine.retry

        last_error: Optional[Exception] = None

        for attempt in range(retry_cfg.max_attempts):
            try:
                result = await self._do_call(
                    provider=provider,
                    model=model,
                    messages=messages,
                    tools=tools,
                    stream=False,
                    temperature=temperature,
                )
                return result

            except APIError as e:
                last_error = e
                if e.status_code in retry_cfg.retryable_codes and attempt < retry_cfg.max_attempts - 1:
                    wait = retry_cfg.backoff_multiplier ** attempt
                    logger.warning(f"⚠️ API 錯誤 {e.status_code}，{wait}s 後重試 (attempt {attempt + 1})")
                    await asyncio.sleep(wait)
                else:
                    raise

        raise last_error or APIError(500, "Max retries exceeded")

    async def _do_call(
        self,
        provider: ProviderConfig,
        model: str,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        stream: bool = False,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """
        實際呼叫 API。
        使用 urllib (同步) 包在 asyncio.to_thread 裡。
        TODO: 未來替換為 httpx 做真正的異步。
        """
        import urllib.request

        endpoint = ModelAdapter.get_endpoint(provider, model)
        headers = ModelAdapter.get_headers(provider)
        payload = ModelAdapter.build_request(
            provider_name=provider.name,
            model=model,
            messages=messages,
            tools=tools,
            stream=False,  # 非串流
            temperature=temperature,
        )

        # Google 用 query param 傳 key
        if provider.name == "google" and provider.api_key:
            endpoint += f"?key={provider.api_key}"

        body = json.dumps(payload).encode("utf-8")

        def _sync_call():
            req = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                error_body = e.read().decode("utf-8") if e.fp else ""
                raise APIError(e.code, f"API Error: {error_body}")

        start = time.time()
        result = await asyncio.to_thread(_sync_call)
        elapsed_ms = int((time.time() - start) * 1000)

        # 記錄呼叫
        input_tokens = result.get("usage", {}).get("prompt_tokens", 0)
        output_tokens = result.get("usage", {}).get("completion_tokens", 0)

        record = APICallRecord(
            model=model,
            provider=provider.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            agent_id="default",
        )
        self._call_history.append(record)

        logger.info(f"✅ API 呼叫完成: {provider.name}/{model} ({elapsed_ms}ms, in:{input_tokens} out:{output_tokens})")
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
