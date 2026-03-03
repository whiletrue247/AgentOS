"""
03_Tool_System — 工具索引 (Catalog)
===================================
管理系統中所有安裝的工具清單。
提供基於 BM25 的零運算工具路由 (Tool Routing)，供 Engine 在不知道有哪些工具時檢索。
支援從/至 catalog.json 的序列化。
"""

import json
import logging
from pathlib import Path
from typing import Optional

from contracts.interfaces import ToolSchema
from config_schema import AgentOSConfig
from paths import get_catalog_path

# 嘗試匯入 BM25Index。由於路徑關係，可能需要絕對或相對匯入。
try:
    from importlib import import_module
    bm25_mod = import_module('02_Memory.bm25_index')
    BM25Index = bm25_mod.BM25Index
except ImportError:
    # 支援直接執行腳本測試時的相對路徑
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from importlib import import_module
    bm25_mod = import_module('02_Memory.bm25_index')
    BM25Index = bm25_mod.BM25Index

logger = logging.getLogger(__name__)


class ToolCatalog:
    def __init__(self, config: Optional[AgentOSConfig] = None, catalog_path: Optional[str] = None):
        self.config = config
        self.catalog_path = Path(catalog_path or get_catalog_path())
        self.tools: dict[str, ToolSchema] = {}
        self.mcp_clients: dict[str, Any] = {} # { server_name: MCPClient }
        self.bm25 = BM25Index()
        
        self.load_catalog()

    async def init_mcp_servers(self) -> None:
        """非同步初始化所有定義在 Config 中的 MCP Server，並拉取工具"""
        if not self.config or not self.config.mcp.servers:
            return
            
        try:
            # 開發環境下動態引入，避免 import 循環
            from importlib import import_module
            mcp_mod = import_module('03_Tool_System.mcp_client')
            MCPClient = mcp_mod.MCPClient
        except ImportError as e:
            logger.error(f"⚠️ 無法載入 MCPClient，略過 MCP Server 初始化: {e}")
            return

        for name, srv_config in self.config.mcp.servers.items():
            if not srv_config.command:
                continue
                
            client = MCPClient(name=name, config=srv_config)
            success = await client.start()
            if success:
                self.mcp_clients[name] = client
                # 拉取工具註冊
                tools = await client.get_tools()
                for t in tools:
                    # mcp_server 的 tools 不需要存檔至 catalog.json，每次啟動動態掛載
                    self.register_tool(t, save=False)
                logger.info(f"🔌 已從 MCP {name} 載入 {len(tools)} 個工具")

    async def shutdown(self) -> None:
        """關閉所有 MCP 連線"""
        for name, client in self.mcp_clients.items():
            await client.stop()
        self.mcp_clients.clear()

    def register_tool(self, tool: ToolSchema, save: bool = True) -> None:
        """
        註冊一個新工具到 Catalog。
        """
        self.tools[tool.name] = tool
        
        # 將 Tool 的描述和參數轉為純文字，加入 BM25 索引
        doc_text = f"{tool.name} {tool.description} " + json.dumps(tool.parameters, ensure_ascii=False)
        self.bm25.add(doc_id=tool.name, text=doc_text, original=tool)
        
        if save:
            self.save_catalog()
            logger.info(f"🔧 已註冊工具: {tool.name} ({tool.install_type})")

    def unregister_tool(self, tool_name: str, save: bool = True) -> bool:
        """
        從 Catalog 移除一個工具。
        """
        if tool_name in self.tools:
            del self.tools[tool_name]
            self.bm25.remove(tool_name)
            if save:
                self.save_catalog()
            logger.info(f"🗑️ 已移除工具: {tool_name}")
            return True
        return False

    def get_tool(self, tool_name: str) -> Optional[ToolSchema]:
        """精確取得指定名稱的工具定義"""
        return self.tools.get(tool_name)

    def search_tools(self, query: str, top_k: int = 5) -> list[ToolSchema]:
        """
        根據使用者任務 (query) 找出最適合的工具。
        使用 BM25 零運算語意路由。
        """
        results = self.bm25.search(query, top_k=top_k)
        return [res[2] for res in results]

    def get_all_tools(self) -> list[ToolSchema]:
        """取得所有已註冊的工具列表"""
        return list(self.tools.values())

    def save_catalog(self) -> None:
        """將目前記憶體內的工具列表寫入 catalog.json"""
        import dataclasses
        
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        dump_data = {}
        for name, tool in self.tools.items():
            dump_data[name] = dataclasses.asdict(tool)
            
        with open(self.catalog_path, "w", encoding="utf-8") as f:
            json.dump(dump_data, f, ensure_ascii=False, indent=2)

    def load_catalog(self) -> None:
        """從 catalog.json 載入工具列表並重建 BM25 索引"""
        if not self.catalog_path.exists():
            return
            
        try:
            with open(self.catalog_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            self.tools.clear()
            self.bm25.clear()
            
            for name, tool_data in data.items():
                tool = ToolSchema(**tool_data)
                self.register_tool(tool, save=False)
                
            logger.info(f"📥 載入 Catalog 完成，共 {len(self.tools)} 個工具")
            
        except Exception as e:
            logger.error(f"❌ 載入 {self.catalog_path} 失敗: {e}")
