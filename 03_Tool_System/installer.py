"""
03_Tool_System — 工具安裝器 (Installer)
=======================================
處理 SYS_TOOL_INSTALL 工具的具體實作。
負責從外部來源下載並驗證工具，將其註冊至 Catalog 中。

支援三種類型:
1. schema_only: 下載 JSON Schema (適用 MCP 或 HTTP API)
2. local_plugin: 下載 Python 腳本到本地 plugins 目錄，並解壓縮其 TOOL_SCHEMA
3. system_package: 將 pip 套件加入到 Sandbox 的 requirements 中

v5.1 新增 (Sprint 2): 工具安全深度掃描
  - AST 危險節點檢測 (exec/eval/compile/subprocess/os.system)
  - 安裝前自動阻擋含危險代碼的工具
"""

import ast
import hashlib
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

    def install(self, tool_name: str, install_type: str, source_url: str, expected_hash: Optional[str] = None) -> bool:
        """
        安裝新工具的主入口
        """
        logger.info(f"🚀 開始安裝工具: {tool_name} (類型: {install_type})")
        
        try:
            if install_type == "schema_only":
                return self._install_schema_only(tool_name, source_url, expected_hash)
            elif install_type == "local_plugin":
                return self._install_local_plugin(tool_name, source_url, expected_hash)
            elif install_type == "system_package":
                return self._install_system_package(tool_name, source_url)
            else:
                logger.error(f"❌ 未知的安裝類型: {install_type}")
                return False
        except Exception as e:
            logger.error(f"❌ 安裝工具 {tool_name} 失敗: {e}")
            return False

    def _verify_trusted_domain(self, url: str) -> bool:
        """驗證是否來自受信任的網域 (Supply Chain Security Allowlist)"""
        # 如果是本地檔案路徑，則放行
        if not url.startswith("http"):
            return True
            
        from urllib.parse import urlparse
        trusted_domains = [
            "raw.githubusercontent.com",
            "github.com",
            "api.github.com",
        ]
        
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            # 支援 exact match 或 sub-domain (如 raw.githubusercontent.com)
            if any(domain == td or domain.endswith("." + td) for td in trusted_domains):
                return True
        except Exception:
            pass
            
        logger.error(f"🔒 安全阻擋: 拒絕從不受信任的網域下載 ({url})。請使用受信任的來源 (如 GitHub)。")
        return False

    def _verify_hash(self, content: bytes, expected_hash: Optional[str]) -> bool:
        if not expected_hash:
            logger.error(f"🔒 安全阻擋: 缺乏 expected_hash！嚴禁下載未經 Checksum 驗證的外部元件。")
            return False
            
        computed = hashlib.sha256(content).hexdigest()
        if computed != expected_hash:
            logger.error(f"🔒 安全阻擋: Checksum 驗證失敗 (Expected: {expected_hash}, Got: {computed})")
            return False
        return True

    def _install_schema_only(self, tool_name: str, source_url: str, expected_hash: Optional[str]) -> bool:
        """
        下載 JSON Schema 並註冊。
        """
        if source_url.startswith("http"):
            if not self._verify_trusted_domain(source_url):
                return False
            req = urllib.request.Request(source_url, headers={'User-Agent': 'AgentOS'})
            with urllib.request.urlopen(req) as response:
                raw_bytes = response.read()
                if not self._verify_hash(raw_bytes, expected_hash):
                    return False
                data = json.loads(raw_bytes.decode('utf-8'))
        else:
            with open(source_url, "rb") as f:
                raw_bytes = f.read()
                if not self._verify_hash(raw_bytes, expected_hash):
                    return False
                data = json.loads(raw_bytes.decode('utf-8'))
                
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

    def _install_local_plugin(self, tool_name: str, source_url: str, expected_hash: Optional[str]) -> bool:
        """
        下載 Python 腳本到 tools/plugins 目錄。
        使用 ast 靜態分析提取 TOOL_SCHEMA，防範 RCE。
        v5.1: 新增危險 AST 節點掃描 (Sprint 2)。
        """
        target_path = self.plugins_dir / f"{tool_name}.py"
        raw_bytes = b""
        
        if source_url.startswith("http"):
            if not self._verify_trusted_domain(source_url):
                return False
            req = urllib.request.Request(source_url, headers={'User-Agent': 'AgentOS'})
            with urllib.request.urlopen(req) as response:
                raw_bytes = response.read()
        else:
            with open(source_url, "rb") as f:
                raw_bytes = f.read()
                
        if not self._verify_hash(raw_bytes, expected_hash):
            return False

        # === Sprint 2: 安全深度掃描 ===
        source_code = raw_bytes.decode('utf-8')
        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            logger.error(f"🔒 安全阻擋: {tool_name} 包含無法解析的 Python 語法: {e}")
            return False

        # 掃描危險 AST 節點
        violations = self._scan_dangerous_ast(tree, tool_name)
        if violations:
            logger.error(
                f"🔒 安全阻擋: {tool_name} 包含 {len(violations)} 個危險調用，拒絕安裝！\n"
                + "\n".join(f"  • {v}" for v in violations)
            )
            return False

        # 通過安全掃描，寫入檔案
        with open(target_path, "wb") as f:
            f.write(raw_bytes)
            
        # 提取 TOOL_SCHEMA
        try:
            schema_dict = None
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == "TOOL_SCHEMA":
                            schema_dict = ast.literal_eval(node.value)
                            break
                if schema_dict is not None:
                    break
                    
            if schema_dict is None:
                logger.error(f"⚠️ 在 {tool_name} 中找不到 TOOL_SCHEMA 變數定義")
                target_path.unlink(missing_ok=True)  # 清理已寫入的檔案
                return False
                
        except Exception as e:
            logger.error(f"⚠️ 解析 {tool_name} 的 Schema 失敗，格式可能不合法: {e}")
            target_path.unlink(missing_ok=True)
            return False
                
        schema = ToolSchema(
            name=tool_name,
            description=schema_dict.get("description", f"Local plugin: {tool_name}"),
            parameters=schema_dict.get("parameters", {"type": "object", "properties": {}}),
            install_type="local_plugin",
            requires_network=schema_dict.get("requires_network", False)
        )
        self.catalog.register_tool(schema)
        logger.info(f"✅ 工具 {tool_name} 安全掃描通過，已安裝")
        return True

    # ========================================
    # Sprint 2: 危險 AST 節點掃描
    # ========================================

    _DANGEROUS_CALLS = {
        # 直接執行任意代碼
        "exec", "eval", "compile", "execfile",
        # 系統命令執行
        "system", "popen", "popen2", "popen3", "popen4",
        # 子程序
        "call", "run", "Popen", "check_output", "check_call",
        # 動態導入
        "__import__", "import_module",
    }

    _DANGEROUS_MODULES = {
        "subprocess", "os", "shutil", "ctypes", "importlib",
        "pty", "commands", "webbrowser",
    }

    def _scan_dangerous_ast(self, tree: ast.AST, tool_name: str) -> list[str]:
        """
        掃描 AST 中的危險節點。
        回傳違規描述列表（空列表 = 安全）。
        """
        violations: list[str] = []

        for node in ast.walk(tree):
            # 1. 檢測危險函數呼叫: exec(), eval(), os.system() 等
            if isinstance(node, ast.Call):
                func_name = self._get_call_name(node)
                if func_name and any(d in func_name for d in self._DANGEROUS_CALLS):
                    violations.append(
                        f"Line {getattr(node, 'lineno', '?')}: "
                        f"危險呼叫 `{func_name}()` — 可能導致任意代碼執行"
                    )

            # 2. 檢測危險模組導入: import subprocess, import os 等
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in self._DANGEROUS_MODULES:
                        violations.append(
                            f"Line {getattr(node, 'lineno', '?')}: "
                            f"危險導入 `import {alias.name}` — 限制模組"
                        )

            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in self._DANGEROUS_MODULES:
                    violations.append(
                        f"Line {getattr(node, 'lineno', '?')}: "
                        f"危險導入 `from {node.module} import ...` — 限制模組"
                    )

        return violations

    @staticmethod
    def _get_call_name(node: ast.Call) -> str:
        """從 AST Call 節點提取函數名稱"""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            parts = []
            current = node.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        return ""


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
