"""
04_Engine — SSE Streamer
========================
處理 LLM API 的串流回應 (Server-Sent Events)。
負責：
  1. 解析 SSE 串流數據
  2. 將 token 片段即時轉發給訂閱者 (Messenger / Dashboard)
  3. 拼接完整回應文本
  4. 偵測 tool_call 事件

使用 Callback 模式，上層模組註冊 on_token / on_complete / on_tool_call。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class StreamChunk:
    """一個串流片段"""
    delta_text: str = ""
    tool_call_id: Optional[str] = None
    tool_call_name: Optional[str] = None
    tool_call_args: Optional[str] = None  # 逐步累積的 JSON 片段
    finish_reason: Optional[str] = None
    raw: Optional[dict] = None


@dataclass
class StreamResult:
    """完整串流結束後的彙整結果"""
    full_text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


# Callback type aliases
OnTokenCallback = Callable[[str], None]             # (delta_text) -> None
OnCompleteCallback = Callable[[StreamResult], None]  # (result) -> None
OnToolCallCallback = Callable[[dict], None]          # (tool_call_dict) -> None


class Streamer:
    """
    SSE 串流處理器。

    用法：
        streamer = Streamer()
        streamer.on_token = lambda text: print(text, end="", flush=True)
        streamer.on_complete = lambda result: print(f"\\nDone: {len(result.full_text)} chars")

        result = streamer.process_sse_lines(sse_lines)
    """

    def __init__(self):
        self.on_token: Optional[OnTokenCallback] = None
        self.on_complete: Optional[OnCompleteCallback] = None
        self.on_tool_call: Optional[OnToolCallCallback] = None

    def process_sse_lines(self, lines: list[str], provider: str = "openai") -> StreamResult:
        """
        處理一批 SSE lines (data: {...}) 並回傳彙整結果。
        """
        result = StreamResult()
        text_parts: list[str] = []
        # 累積 tool calls: { index: { id, name, args_parts } }
        tool_call_accum: dict[int, dict] = {}

        for line in lines:
            line = line.strip()
            if not line or line == "data: [DONE]":
                continue
            if line.startswith("data: "):
                line = line[6:]

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            chunk = self._parse_chunk(data, provider)
            if not chunk:
                continue

            # 文字片段
            if chunk.delta_text:
                text_parts.append(chunk.delta_text)
                if self.on_token:
                    self.on_token(chunk.delta_text)

            # Tool call 片段 (逐步累積)
            if chunk.tool_call_name is not None or chunk.tool_call_args is not None:
                idx = 0  # 預設 index
                if chunk.raw:
                    # 從 raw 中取 tool_calls[0].index
                    tc_list = chunk.raw.get("choices", [{}])[0].get("delta", {}).get("tool_calls", [])
                    if tc_list:
                        idx = tc_list[0].get("index", 0)

                if idx not in tool_call_accum:
                    tool_call_accum[idx] = {"id": "", "name": "", "args_parts": []}

                if chunk.tool_call_id:
                    tool_call_accum[idx]["id"] = chunk.tool_call_id
                if chunk.tool_call_name:
                    tool_call_accum[idx]["name"] = chunk.tool_call_name
                if chunk.tool_call_args:
                    tool_call_accum[idx]["args_parts"].append(chunk.tool_call_args)

            # Finish reason
            if chunk.finish_reason:
                result.finish_reason = chunk.finish_reason

        # 彙整
        result.full_text = "".join(text_parts)

        for idx in sorted(tool_call_accum.keys()):
            tc = tool_call_accum[idx]
            args_str = "".join(tc["args_parts"])
            try:
                args = json.loads(args_str) if args_str else {}
            except json.JSONDecodeError:
                args = {"_raw": args_str}

            tool_call_dict = {
                "id": tc["id"],
                "name": tc["name"],
                "arguments": args,
            }
            result.tool_calls.append(tool_call_dict)

            if self.on_tool_call:
                self.on_tool_call(tool_call_dict)

        if self.on_complete:
            self.on_complete(result)

        return result

    def _parse_chunk(self, data: dict, provider: str) -> Optional[StreamChunk]:
        """解析單一 SSE JSON chunk"""

        if provider in ("openai", "deepseek", "groq", "ollama"):
            return self._parse_openai_chunk(data)
        elif provider == "anthropic":
            return self._parse_anthropic_chunk(data)
        elif provider == "google":
            return self._parse_google_chunk(data)

        # Fallback: 嘗試 OpenAI 格式
        return self._parse_openai_chunk(data)

    def _parse_openai_chunk(self, data: dict) -> Optional[StreamChunk]:
        choices = data.get("choices", [])
        if not choices:
            return None

        choice = choices[0]
        delta = choice.get("delta", {})
        finish = choice.get("finish_reason")

        chunk = StreamChunk(
            delta_text=delta.get("content", "") or "",
            finish_reason=finish,
            raw=data,
        )

        # Tool calls
        tool_calls = delta.get("tool_calls", [])
        if tool_calls:
            tc = tool_calls[0]
            chunk.tool_call_id = tc.get("id")
            func = tc.get("function", {})
            chunk.tool_call_name = func.get("name")
            chunk.tool_call_args = func.get("arguments")

        return chunk

    def _parse_anthropic_chunk(self, data: dict) -> Optional[StreamChunk]:
        event_type = data.get("type", "")

        if event_type == "content_block_delta":
            delta = data.get("delta", {})
            if delta.get("type") == "text_delta":
                return StreamChunk(delta_text=delta.get("text", ""))
            if delta.get("type") == "input_json_delta":
                return StreamChunk(tool_call_args=delta.get("partial_json", ""))

        if event_type == "content_block_start":
            block = data.get("content_block", {})
            if block.get("type") == "tool_use":
                return StreamChunk(
                    tool_call_id=block.get("id"),
                    tool_call_name=block.get("name"),
                )

        if event_type == "message_delta":
            return StreamChunk(finish_reason=data.get("delta", {}).get("stop_reason"))

        return None

    def _parse_google_chunk(self, data: dict) -> Optional[StreamChunk]:
        candidates = data.get("candidates", [])
        if not candidates:
            return None

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if not parts:
            return None

        text = parts[0].get("text", "")
        finish = candidates[0].get("finishReason")

        return StreamChunk(delta_text=text, finish_reason=finish)
