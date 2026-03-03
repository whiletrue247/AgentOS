"""
04_Engine — 主事件循環 (Engine)
===============================
AgentOS 的心臟。
把所有零件串在一起：Gateway → RateLimiter → Streamer → ToolSystem → Memory。

事件驅動架構：
  1. 收到 USER_MESSAGE
  2. 組裝 System Prompt (SOUL + Memory Context)
  3. 呼叫 LLM API (經 RateLimiter 節流)
  4. 若 LLM 回覆 tool_call → 交給 ToolSystem 執行 → 結果回傳 LLM → 重複
  5. 若 LLM 回覆文字 → 發送 AGENT_RESPONSE 事件 → 結束
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

from config_schema import AgentOSConfig
from contracts.interfaces import (
    EngineEvent,
    EventType,
    ToolCallRequest,
    ToolCallResult,
)

logger = logging.getLogger(__name__)

# Callback type
EventHandler = Callable[[EngineEvent], Any]

# 最大 API 重試次數
MAX_API_RETRIES = 2


def _is_retryable(error: Exception) -> bool:
    """
    判斷 API 錯誤是否可重試。
    可重試：Timeout、429 (Rate Limit)、5xx (Server Error)
    不可重試：401/403 (Auth)、400 (Bad Request)、其他未知錯誤
    """
    error_str = str(error).lower()
    error_type = type(error).__name__.lower()

    # Timeout 類錯誤
    if "timeout" in error_str or "timeout" in error_type:
        return True

    # 連線錯誤
    if "connection" in error_str or "connect" in error_type:
        return True

    # HTTP status code 判斷
    status_code = getattr(error, "status_code", None)
    if status_code is not None:
        # 429 Rate Limit、5xx Server Error 可重試
        if status_code == 429 or 500 <= status_code < 600:
            return True
        # 4xx Client Error 不可重試
        if 400 <= status_code < 500:
            return False

    # 檢查錯誤訊息中的 status code
    if "429" in error_str or "rate limit" in error_str:
        return True
    if any(f"{code}" in error_str for code in range(500, 504)):
        return True

    # 預設不重試（保守策略）
    return False


class Engine:
    """
    AgentOS 主引擎。
    管理 ReAct Loop 的核心邏輯。
    """

    def __init__(self, config: AgentOSConfig):
        self.config = config

        # 子模組會在啟動時注入（避免循環 import）
        self._gateway: Any = None          # APIGateway
        self._rate_limiter: Any = None     # RateLimiter
        self._streamer: Any = None         # Streamer
        self._tool_executor: Any = None    # Callable(ToolCallRequest) -> ToolCallResult
        self._memory_manager: Any = None   # MemoryManager
        self._soul_content: str = ""       # SOUL.md 內容

        # Event Bus
        self._handlers: dict[EventType, list[EventHandler]] = {}

        # Task Queue
        self._task_queue: asyncio.Queue[EngineEvent] = asyncio.Queue()

        # Watchdog
        self._step_count = 0

        logger.info("🫀 Engine 初始化完成")

    # ========================================
    # 模組注入
    # ========================================

    def inject(
        self,
        gateway: Any = None,
        rate_limiter: Any = None,
        streamer: Any = None,
        tool_executor: Any = None,
        memory_manager: Any = None,
        soul_content: str = "",
    ) -> None:
        """注入子模組。在 main.py 中呼叫。"""
        if gateway:
            self._gateway = gateway
        if rate_limiter:
            self._rate_limiter = rate_limiter
        if streamer:
            self._streamer = streamer
        if tool_executor:
            self._tool_executor = tool_executor
        if memory_manager:
            self._memory_manager = memory_manager
        if soul_content:
            self._soul_content = soul_content

    # ========================================
    # Event Bus
    # ========================================

    def on(self, event_type: EventType, handler: EventHandler) -> None:
        """註冊事件處理器"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    async def emit(self, event: EngineEvent) -> None:
        """發送事件到 Event Bus"""
        handlers = self._handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"❌ Event handler error: {e}")

    # ========================================
    # 核心 ReAct Loop
    # ========================================

    async def handle_message(
        self,
        user_message: str,
        agent_id: str = "default",
        conversation_history: Optional[list[dict]] = None,
    ) -> str:
        """
        處理一則使用者訊息，回傳 Agent 的最終回覆。
        這是 Engine 的主入口。
        """
        self._step_count = 0
        max_steps = self.config.engine.watchdog.max_steps

        # 組裝對話歷史
        messages = conversation_history or []

        # 注入 System Prompt (SOUL + Memory Context)
        system_prompt = self._soul_content or "You are a helpful AI Agent."

        # 嘗試從 Memory 中取得相關上下文
        if self._memory_manager:
            try:
                memory_ctx = await self._memory_manager.get_relevant_context(
                    query=user_message, agent_id=agent_id
                )
                if memory_ctx:
                    system_prompt += f"\n\n{memory_ctx}"
            except Exception as e:
                logger.warning(f"⚠️ Memory context 取得失敗: {e}")

        # 確保 system message 在最前面
        if not messages or messages[0].get("role") != "system":
            messages.insert(0, {"role": "system", "content": system_prompt})
        else:
            messages[0]["content"] = system_prompt

        # 加入使用者訊息
        messages.append({"role": "user", "content": user_message})

        # 發送 USER_MESSAGE 事件
        await self.emit(EngineEvent(
            event_type=EventType.USER_MESSAGE,
            payload={"message": user_message, "agent_id": agent_id},
        ))

        # ReAct Loop
        while self._step_count < max_steps:
            self._step_count += 1
            logger.info(f"🔄 ReAct Step {self._step_count}/{max_steps}")

            # Rate limit
            if self._rate_limiter:
                estimated_tokens = sum(len(m.get("content") or "") // 4 for m in messages)
                await self._rate_limiter.acquire(estimated_tokens)

            # 呼叫 LLM（含自動重試）
            if not self._gateway:
                return "❌ Engine Error: No API Gateway configured."

            response = None
            last_error: Optional[Exception] = None
            for attempt in range(MAX_API_RETRIES + 1):
                try:
                    response = await self._gateway.call(
                        messages=messages,
                        agent_id=agent_id,
                        stream=False,
                    )
                    break  # 成功，跳出重試迴圈
                except Exception as e:
                    last_error = e
                    if attempt < MAX_API_RETRIES and _is_retryable(e):
                        wait_seconds = 2 ** attempt  # 1s, 2s 指數退避
                        logger.warning(
                            f"⚠️ API 呼叫失敗 (重試 {attempt + 1}/{MAX_API_RETRIES})，"
                            f"等待 {wait_seconds}s 後重試: {e}"
                        )
                        await asyncio.sleep(wait_seconds)
                    else:
                        logger.error(f"❌ API call failed (不可重試): {e}")
                        return f"❌ API Error: {e}"

            if response is None:
                logger.error(f"❌ API call exhausted all retries: {last_error}")
                return f"❌ API Error (重試耗盡): {last_error}"

            # 解析回應
            choice = response.get("choices", [{}])[0]
            message = choice.get("message", {})
            choice.get("finish_reason", "")

            # Case 1: Tool calls
            tool_calls = message.get("tool_calls", [])
            if tool_calls:
                # 把 assistant message (含 tool_calls) 加入歷史
                messages.append(message)

                for tc in tool_calls:
                    func = tc.get("function", {})
                    tool_name = func.get("name", "")
                    try:
                        tool_args = __import__("json").loads(func.get("arguments", "{}"))
                    except Exception:
                        tool_args = {}

                    logger.info(f"🔧 Tool call: {tool_name}({tool_args})")

                    # 發送 TOOL_CALL 事件
                    await self.emit(EngineEvent(
                        event_type=EventType.TOOL_CALL,
                        payload={"tool_name": tool_name, "arguments": tool_args},
                    ))

                    # 執行工具
                    if self._tool_executor:
                        req = ToolCallRequest(
                            tool_name=tool_name,
                            arguments=tool_args,
                        )
                        try:
                            result = await self._tool_executor(req)
                        except Exception as e:
                            result = ToolCallResult(
                                tool_name=tool_name, success=False,
                                output="", error=str(e),
                            )
                    else:
                        result = ToolCallResult(
                            tool_name=tool_name, success=False,
                            output="", error="No tool executor configured",
                        )

                    # 把 tool result 加入歷史
                    tool_output = result.output if result.success else f"Error: {result.error}"
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": tool_output,
                    })

                    # 發送 TOOL_RESULT 事件
                    await self.emit(EngineEvent(
                        event_type=EventType.TOOL_RESULT,
                        payload={"tool_name": tool_name, "output": tool_output},
                    ))

                # 繼續 Loop（讓 LLM 看到 tool result）
                continue

            # Case 2: 純文字回覆
            content = message.get("content", "")
            messages.append({"role": "assistant", "content": content})

            # 發送 AGENT_RESPONSE 事件
            await self.emit(EngineEvent(
                event_type=EventType.AGENT_RESPONSE,
                payload={"content": content, "agent_id": agent_id},
            ))

            return content

        # Watchdog: 超過最大步數
        logger.error(f"🚨 Watchdog: 超過 {max_steps} 步，強制中止")
        return f"⚠️ Agent 達到最大步數限制 ({max_steps})，任務中止。"
