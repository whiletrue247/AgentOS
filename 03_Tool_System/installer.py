"""
03_Tool_System — 工具安裝器 (Installer)
=======================================
處理 SYS_TOOL_INSTALL 工具的具體實作。
負責從外部來源下載並驗證工具，將其註冊至 Catalog 中。

支援三種類型:
1. schema_only: 下載 JSON Schema (適用 MCP 或 HTTP API)
2. local_plugin: 下載 Python 腳本到本地 plugins 目錄，並解壓縮其 TOOL_SCHEMA
3. system_package: 將 pip 套件加入到 Sandbox 的 requirements 中
"""

import json
import logging
import urllib.request
from pathlib import Path
from typing import Optional

from contracts.interfaces import ToolSchema
from paths import get_tools_dir
# 在開發環境中，直接匯入 catalog 模組
try:
    from .catalog import ToolCatalog
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from importlib import import_module
    catalog_mod = import_module('03_Tool_System.catalog')
    ToolCatalog = catalog_mod.ToolCatalog

logger = logging.getLogger(__name__)


class ToolInstaller:
    """負責各種工具的外置安裝與下載"""

    def __init__(self, catalog: ToolCatalog, tools_dir: Optional[str] = None):
        self.catalog = catalog
        self.tools_dir = Path(tools_dir) if tools_dir else get_tools_dir()
        self.plugins_dir = self.tools_dir / "plugins"
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self.req_file = self.tools_dir / "sandbox_requirements.txt"

    def install(self, tool_name: str, install_type: str, source_url: str) -> bool:
        """
        安裝新工具的主入口
        """
        logger.info(f"🚀 開始安裝工具: {tool_name} (類型: {install_type})")
        
        try:
            if install_type == "schema_only":
                return self._install_schema_only(tool_name, source_url)
            elif install_type == "local_plugin":
                return self._install_local_plugin(tool_name, source_url)
            elif install_type == "system_package":
                return self._install_system_package(tool_name, source_url)
            else:
                logger.error(f"❌ 未知的安裝類型: {install_type}")
                return False
        except Exception as e:
            logger.error(f"❌ 安裝工具 {tool_name} 失敗: {e}")
            return False

    def _install_schema_only(self, tool_name: str, source_url: str) -> bool:
        """
        下載 JSON Schema 並註冊。
        source_url 必須回傳一個 JSON 物件，包含 description, parameters 等。
        """
        if source_url.startswith("http"):
            req = urllib.request.Request(source_url, headers={'User-Agent': 'AgentOS'})
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode('utf-8'))
        else:
            with open(source_url, "r", encoding="utf-8") as f:
                data = json.load(f)
                
        schema = ToolSchema(
            name=tool_name,
            description=data.get("description", ""),
            parameters=data.get("parameters", {"type": "object", "properties": {}}),
            install_type="schema_only",
            requires_network=data.get("requires_network", True),
            mcp_server=data.get("mcp_server")
        )
        self.catalog.register_tool(schema)
        return True

    def _install_local_plugin(self, tool_name: str, source_url: str) -> bool:
        """
        下載 Python 腳本到 tools/plugins 目錄。
        腳本內應包含 `TOOL_SCHEMA` 字典。
        """
        target_path = self.plugins_dir / f"{tool_name}.py"
        
        if source_url.startswith("http"):
            req = urllib.request.Request(source_url, headers={'User-Agent': 'AgentOS'})
            with urllib.request.urlopen(req) as response:
                with open(target_path, "wb") as f:
                    f.write(response.read())
        else:
            import shutil
            shutil.copy(source_url, target_path)
            
        # 動態載入腳本並提取 TOOL_SCHEMA
        import importlib.util
        spec = importlib.util.spec_from_file_location(tool_name, target_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
                schema_dict = getattr(module, 'TOOL_SCHEMA', {})
                
                schema = ToolSchema(
                    name=tool_name,
                    description=schema_dict.get("description", f"Local plugin: {tool_name}"),
                    parameters=schema_dict.get("parameters", {"type": "object", "properties": {}}),
                    install_type="local_plugin",
                    requires_network=schema_dict.get("requires_network", False)
                )
                self.catalog.register_tool(schema)
                return True
            except Exception as e:
                logger.error(f"⚠️ 無法載入本地外掛 {tool_name}，可能語法錯誤: {e}")
                return False
                
        return False

    def _install_system_package(self, tool_name: str, source_url: str) -> bool:
        """
        將 pip 套件加入到 Sandbox 的 requirements 中，
        這個類型的 tools 雖然註冊進 Catalog，但在被呼叫時，
        主要是告知 Agent "你可以在 Sandbox 中 import 這個套件來寫 Code"。
        source_url 在此處代表 pip package name (例如: requests, numpy)
        """
        schema = ToolSchema(
            name=tool_name,
            description=f"System package ({source_url}) available in Sandbox environment. Use `import {source_url}` in your python code.",
            parameters={"type": "object", "properties": {}},
            install_type="system_package",
            requires_network=False
        )
        self.catalog.register_tool(schema)
        
        # 寫入 sandbox_requirements.txt
        existing_packages = set()
        if self.req_file.exists():
            with open(self.req_file, "r") as f:
                existing_packages = set(line.strip() for line in f if line.strip())
                
        if source_url not in existing_packages:
            with open(self.req_file, "a") as f:
                f.write(f"{source_url}\n")
                
        logger.info(f"✅ 已將 {source_url} 加入 Sandbox 可用套件清單")
        return True
