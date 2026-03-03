"""
contracts/protocol_gateway.py — 協議閘道抽象層 (Sprint 4)
==========================================================
統一 A2A + MCP 的訊息格式轉換層，為未來 ACP 通用協議打底。

設計理念：
  - 所有外部協議的訊息都先轉換成 UnifiedMessage
  - 由 ProtocolGateway 路由到對應的 Adapter
  - 新增協議只需實作 ProtocolAdapter 介面

支援的協議：
  - A2A (Agent-to-Agent): 多 Agent 編排訊息
  - MCP (Model Context Protocol): 工具呼叫協議
  - HTTP Webhook: 外部服務 callback
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "ProtocolGateway",
    "ProtocolAdapter",
    "UnifiedMessage",
    "MessageDirection",
]


class MessageDirection:
    INBOUND = "inbound"
    OUTBOUND = "outbound"


@dataclass
class UnifiedMessage:
    """
    統一訊息格式 — 所有協議的訊息都轉換成此格式。

    這是協議閘道的核心抽象：無論訊息來自 A2A、MCP 還是 HTTP，
    閘道都只處理 UnifiedMessage。
    """
    message_id: str
    protocol: str           # "a2a" | "mcp" | "http" | "acp"
    direction: str          # "inbound" | "outbound"
    source: str             # 來源 (agent_id, tool_name, URL)
    target: str             # 目標
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""


class ProtocolAdapter(ABC):
    """
    協議適配器介面。
    每個協議 (A2A, MCP, HTTP, 未來的 ACP) 各實作一個。
    """

    @property
    @abstractmethod
    def protocol_name(self) -> str:
        """協議名稱"""
        ...

    @abstractmethod
    async def encode(self, message: UnifiedMessage) -> bytes:
        """將 UnifiedMessage 編碼為協議特定格式"""
        ...

    @abstractmethod
    async def decode(self, raw: bytes) -> UnifiedMessage:
        """將協議特定格式解碼為 UnifiedMessage"""
        ...

    @abstractmethod
    async def send(self, message: UnifiedMessage) -> bool:
        """發送訊息"""
        ...


class A2AAdapter(ProtocolAdapter):
    """A2A 協議適配器"""

    @property
    def protocol_name(self) -> str:
        return "a2a"

    async def encode(self, message: UnifiedMessage) -> bytes:
        import json
        return json.dumps({
            "type": "a2a_message",
            "from": message.source,
            "to": message.target,
            "payload": message.payload,
            "metadata": message.metadata,
        }, ensure_ascii=False).encode("utf-8")

    async def decode(self, raw: bytes) -> UnifiedMessage:
        import json
        data = json.loads(raw)
        return UnifiedMessage(
            message_id=data.get("id", ""),
            protocol="a2a",
            direction=MessageDirection.INBOUND,
            source=data.get("from", ""),
            target=data.get("to", ""),
            payload=data.get("payload", {}),
            metadata=data.get("metadata", {}),
            timestamp=datetime.now().isoformat(),
        )

    async def send(self, message: UnifiedMessage) -> bool:
        encoded = await self.encode(message)
        logger.info(f"📤 A2A send: {message.source} → {message.target} ({len(encoded)} bytes)")
        # 實際發送由 A2ABus 處理
        return True


class MCPAdapter(ProtocolAdapter):
    """MCP (Model Context Protocol) 適配器"""

    @property
    def protocol_name(self) -> str:
        return "mcp"

    async def encode(self, message: UnifiedMessage) -> bytes:
        import json
        return json.dumps({
            "jsonrpc": "2.0",
            "method": message.payload.get("method", "tools/call"),
            "params": message.payload.get("params", {}),
            "id": message.message_id,
        }, ensure_ascii=False).encode("utf-8")

    async def decode(self, raw: bytes) -> UnifiedMessage:
        import json
        data = json.loads(raw)
        return UnifiedMessage(
            message_id=str(data.get("id", "")),
            protocol="mcp",
            direction=MessageDirection.INBOUND,
            source="mcp_server",
            target="engine",
            payload={
                "method": data.get("method", ""),
                "params": data.get("params", {}),
                "result": data.get("result"),
            },
            timestamp=datetime.now().isoformat(),
        )

    async def send(self, message: UnifiedMessage) -> bool:
        encoded = await self.encode(message)
        logger.info(f"📤 MCP send: {message.payload.get('method', '?')} ({len(encoded)} bytes)")
        return True


class ProtocolGateway:
    """
    協議閘道 — 統一管理所有協議適配器。

    使用方式：
        gw = ProtocolGateway()
        gw.register_adapter(A2AAdapter())
        gw.register_adapter(MCPAdapter())

        msg = UnifiedMessage(...)
        await gw.route(msg)
    """

    def __init__(self):
        self._adapters: Dict[str, ProtocolAdapter] = {}
        self._message_log: List[UnifiedMessage] = []
        logger.info("🌐 ProtocolGateway 初始化完成")

    def register_adapter(self, adapter: ProtocolAdapter) -> None:
        """註冊協議適配器"""
        self._adapters[adapter.protocol_name] = adapter
        logger.info(f"🔌 協議適配器已註冊: {adapter.protocol_name}")

    def get_adapter(self, protocol: str) -> Optional[ProtocolAdapter]:
        """取得指定協議的適配器"""
        return self._adapters.get(protocol)

    async def route(self, message: UnifiedMessage) -> bool:
        """
        路由訊息到對應的協議適配器。
        """
        adapter = self._adapters.get(message.protocol)
        if not adapter:
            logger.error(f"❌ 未知協議: {message.protocol}")
            return False

        self._message_log.append(message)
        success = await adapter.send(message)

        if success:
            logger.debug(
                f"✅ 訊息路由成功: {message.protocol} "
                f"{message.source} → {message.target}"
            )
        return success

    async def receive(self, protocol: str, raw: bytes) -> Optional[UnifiedMessage]:
        """
        接收並解碼來自外部協議的訊息。
        """
        adapter = self._adapters.get(protocol)
        if not adapter:
            logger.error(f"❌ 無法解碼未知協議: {protocol}")
            return None

        try:
            message = await adapter.decode(raw)
            self._message_log.append(message)
            return message
        except Exception as e:
            logger.error(f"❌ 訊息解碼失敗 ({protocol}): {e}")
            return None

    @property
    def supported_protocols(self) -> List[str]:
        """列出已註冊的協議"""
        return list(self._adapters.keys())

    def get_message_log(self, last_n: int = 20) -> List[UnifiedMessage]:
        """取得最近的訊息日誌（供 Dashboard 使用）"""
        return self._message_log[-last_n:]
