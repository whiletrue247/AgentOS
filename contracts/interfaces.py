"""
AgentOS Interface Contracts
===========================
所有模組間的通訊介面定義。
任何模組的實作都必須遵守這些介面，確保可替換性。

模組對照：
  01_Kernel   → KernelConfig
  02_Memory   → MemoryProvider, UnifiedMemoryItem
  03_Tool_System → SandboxProvider, ToolCallRequest, ToolCallResult, ToolSchema
  04_Engine   → EngineEvent, CostReport
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Protocol, runtime_checkable


# ============================================================
# 01_Kernel — 靈魂載入器
# ============================================================

@dataclass
class KernelConfig:
    """Kernel 啟動時讀取的設定"""
    soul_path: str = "./SOUL.md"
    soul_content: str = ""  # 載入後的純文字內容


# ============================================================
# 02_Memory — 統一記憶數據元
# ============================================================

@dataclass
class UnifiedMemoryItem:
    """跨後端的萬用記憶格式"""
    memory_id: str
    content: str
    content_type: str  # "fact" | "event" | "preference" | "task" | "conversation"
    importance: float = 0.5  # 0.0 ~ 1.0

    # 時序
    t_created: datetime = field(default_factory=datetime.now)
    t_valid: Optional[datetime] = None
    t_invalid: Optional[datetime] = None

    # 關聯
    relationships: list[str] = field(default_factory=list)  # 關聯的 memory_id 列表

    # 可選向量
    embedding: Optional[list[float]] = None
    provider_hint: Optional[str] = None  # 原始 Provider 名稱

    # 自由擴充
    metadata: dict[str, Any] = field(default_factory=dict)
    # metadata.custom_tags: list[str]  → 用於 agent_id 私有記憶區分
    # metadata.preference_signal: dict → 行為反饋學習迴路


@runtime_checkable
class MemoryProvider(Protocol):
    """Memory 後端的統一介面。SQLite / PgVector / Obsidian 都實作此介面。"""

    async def write(self, item: UnifiedMemoryItem) -> None:
        """寫入或更新一條記憶"""
        ...

    async def read(self, memory_id: str) -> Optional[UnifiedMemoryItem]:
        """根據 ID 讀取單條記憶"""
        ...

    async def search(
        self,
        query: str,
        top_k: int = 5,
        min_importance: float = 0.0,
        content_type: Optional[str] = None,
    ) -> list[UnifiedMemoryItem]:
        """搜索記憶 (BM25 或向量檢索由 Provider 自行實作)"""
        ...

    async def delete(self, memory_id: str) -> bool:
        """刪除一條記憶"""
        ...

    async def list_by_tags(self, tags: list[str], top_k: int = 10) -> list[UnifiedMemoryItem]:
        """根據 custom_tags 列出記憶"""
        ...


# ============================================================
# 03_Tool_System — 工具系統
# ============================================================

@dataclass
class ToolSchema:
    """工具的 JSON Schema 描述 (符合 OpenAI function calling 格式)"""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema 格式
    install_type: str = "schema_only"  # "schema_only" | "local_plugin" | "system_package"
    requires_network: bool = False
    mcp_server: Optional[str] = None  # MCP Server URL (Schema-only 類型使用)


@dataclass
class ToolCallRequest:
    """Engine 呼叫 Tool System 的請求格式"""
    tool_name: str
    arguments: dict[str, Any]
    timeout_seconds: int = 60
    network_allowed: Optional[bool] = None  # None = 使用 config 預設值


@dataclass
class ToolCallResult:
    """Tool System 回傳給 Engine 的結果"""
    tool_name: str
    success: bool
    output: str  # 已經過 Truncator 截斷的輸出
    error: Optional[str] = None
    execution_time_ms: int = 0
    truncated: bool = False  # 是否被截斷過


class SandboxType(enum.Enum):
    """沙盒類型"""
    DOCKER = "docker"          # Docker 容器強隔離 (預設)
    PYODIDE = "pyodide"        # WASM，本地瞬間
    E2B = "e2b"                # 雲端 MicroVM


@runtime_checkable
class SandboxProvider(Protocol):
    """沙盒執行環境的統一介面。Pyodide / E2B / Subprocess 都實作此介面。"""

    async def execute(
        self,
        code: str,
        language: str,  # "python" | "bash" | "javascript"
        timeout_seconds: int = 60,
        network_allowed: bool = False,
    ) -> ToolCallResult:
        """在沙盒內執行代碼"""
        ...

    async def cleanup(self) -> None:
        """清理沙盒環境"""
        ...


# ============================================================
# 04_Engine — 心臟引擎
# ============================================================

class EventType(enum.Enum):
    """Engine Event Bus 的事件類型"""
    USER_MESSAGE = "user_message"          # 使用者發來訊息
    AGENT_RESPONSE = "agent_response"      # Agent 回覆
    TOOL_CALL = "tool_call"                # Agent 要呼叫工具
    TOOL_RESULT = "tool_result"            # 工具執行結果
    TASK_COMPLETE = "task_complete"         # 任務完成
    ASK_HUMAN = "ask_human"                # Agent 向人類求助
    HUMAN_REPLY = "human_reply"            # 人類回覆求助
    A2A_MESSAGE = "a2a_message"            # Agent 間通訊
    BUDGET_WARNING = "budget_warning"      # 預算即將到達上限
    BUDGET_EXCEEDED = "budget_exceeded"    # 預算已超標
    ERROR = "error"                        # 錯誤


@dataclass
class EngineEvent:
    """Engine Event Bus 上流通的事件"""
    event_type: EventType
    payload: dict[str, Any]
    source_agent: str = "default"     # 發送方 agent_id
    target_agent: Optional[str] = None  # 接收方 agent_id (None = 廣播)
    timestamp: datetime = field(default_factory=datetime.now)
    event_id: str = ""  # 唯一 ID，自動生成


@dataclass
class CostReport:
    """Dashboard 顯示的 Token 消耗數據"""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_m: float = 0.0  # 總共消耗多少 M (百萬 Token)
    daily_m: float = 0.0  # 今日消耗
    daily_limit_m: float = 1.0  # 每日上限
    budget_remaining_pct: float = 100.0  # 剩餘百分比
    calls_today: int = 0  # 今日 API 呼叫次數
    history: list[dict[str, Any]] = field(default_factory=list)
    # history item: { "date": "2026-03-03", "input_m": 0.2, "output_m": 0.1 }


@dataclass
class APICallRecord:
    """單次 API 呼叫的紀錄 (用於 Cost Guard 計量)"""
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    timestamp: datetime = field(default_factory=datetime.now)
    cached: bool = False  # 是否命中 Prompt Cache
    agent_id: str = "default"


# ============================================================
# SYS_ASK_HUMAN — Agent 向人類求助的結構
# ============================================================

@dataclass
class HumanRequest:
    """Agent 透過 SYS_ASK_HUMAN 發送的求助請求"""
    question: str
    context: str = ""  # 附加上下文
    options: list[str] = field(default_factory=list)  # 可選的快速回覆選項
    timeout_minutes: int = 30  # 等待多久後自動跳過
    blocking: bool = True  # 是否阻塞等待回覆


@dataclass
class HumanResponse:
    """人類對 SYS_ASK_HUMAN 的回覆"""
    answer: str
    responded: bool = True  # False = 超時未回覆
    timestamp: datetime = field(default_factory=datetime.now)
