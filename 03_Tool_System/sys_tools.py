"""
03_Tool_System — 系統工具定義 (System Tools)
============================================
定義 OS 核心不可卸載的 5 個系統工具：
1. SYS_TOOL_SEARCH: 模糊搜尋目前有什麼工具可用 (利用 BM25 路由)
2. SYS_TOOL_INSTALL: 安裝外部新工具
3. SYS_TASK_COMPLETE: 標記任務完成，並提供最終輸出
4. SYS_ROLLBACK: 版本回滾 (復原錯誤的操作)
5. SYS_ASK_HUMAN: 卡關時向人類求助或請求授權

這些工具不會丟進 Sandbox 執行，而是由 OS 核心 (Engine / ToolSystem) 直接攔截處理。
"""

from contracts.interfaces import ToolSchema

SYS_TOOL_SEARCH = ToolSchema(
    name="SYS_TOOL_SEARCH",
    description=(
        "Search the Tool Catalog for available tools based on your current need. "
        "Use this when you don't know which tool to use. "
        "Returns a list of matching tool names and descriptions."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language description of what you want to do (e.g., 'search web', 'parse pdf')"
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results to return (default 5)",
                "default": 5
            }
        },
        "required": ["query"]
    },
    install_type="system",
    requires_network=False
)

SYS_TOOL_INSTALL = ToolSchema(
    name="SYS_TOOL_INSTALL",
    description=(
        "Install a new tool into the AgentOS Tool Catalog. "
        "Supports 3 install types: 'schema_only' (MCP servers/APIs), "
        "'local_plugin' (downloaded python scripts), and 'system_package' (pip install in Sandbox)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "tool_name": {
                "type": "string",
                "description": "Name of the new tool"
            },
            "install_type": {
                "type": "string",
                "enum": ["schema_only", "local_plugin", "system_package"],
                "description": "The installation method"
            },
            "source_url": {
                "type": "string",
                "description": "URL to the MCP spec, plugin file, or pip package name"
            }
        },
        "required": ["tool_name", "install_type", "source_url"]
    },
    install_type="system",
    requires_network=True
)

SYS_TASK_COMPLETE = ToolSchema(
    name="SYS_TASK_COMPLETE",
    description=(
        "Mark the current primary task as completed and provide the final result or summary to the user."
    ),
    parameters={
        "type": "object",
        "properties": {
            "final_result": {
                "type": "string",
                "description": "The final answer, output, or summary of the completed task."
            }
        },
        "required": ["final_result"]
    },
    install_type="system",
    requires_network=False
)

SYS_ROLLBACK = ToolSchema(
    name="SYS_ROLLBACK",
    description=(
        "Rollback system state (e.g., config files, installed tools) to a previous stable state "
        "if an error occurs or a bad change was made."
    ),
    parameters={
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "What to rollback (e.g., 'config', 'tool:some_tool_name')"
            },
            "reason": {
                "type": "string",
                "description": "Reason for the rollback"
            }
        },
        "required": ["target"]
    },
    install_type="system",
    requires_network=False
)

SYS_ASK_HUMAN = ToolSchema(
    name="SYS_ASK_HUMAN",
    description=(
        "Ask the human user a question, request missing information, or ask for explicit confirmation/authorization. "
        "Use this only when absolutely necessary (e.g., CAPTCHA, 2FA, ambiguous instructions, destructive actions), "
        "as it pauses the Agent's execution until the user replies."
    ),
    parameters={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The clear and concise question for the user"
            },
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of quick-reply options (e.g., ['Yes', 'No', 'Abort'])"
            },
            "blocking": {
                "type": "boolean",
                "description": "Whether to pause execution and wait for the response (default true)",
                "default": True
            }
        },
        "required": ["question"]
    },
    install_type="system",
    requires_network=False
)

# 方便匯出所有系統工具
SYSTEM_TOOLS = [
    SYS_TOOL_SEARCH,
    SYS_TOOL_INSTALL,
    SYS_TASK_COMPLETE,
    SYS_ROLLBACK,
    SYS_ASK_HUMAN
]

def register_system_tools(catalog) -> None:
    """將此 5 個系統工具強行注入到 Catalog 中"""
    for tool in SYSTEM_TOOLS:
        catalog.register_tool(tool, save=False)
