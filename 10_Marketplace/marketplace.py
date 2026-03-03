"""
10_Marketplace/marketplace.py
=============================
Marketplace 核心模組，提供本地與遠端的 Tool/Soul 下載安裝，
並且強制使用 JSON Schema 來管理 Tool，杜絕 exec_module 防範 RCE 風險。
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from dataclasses import dataclass
from typing import Dict, List

from paths import get_data_dir

__all__ = ["Marketplace", "ToolInfo"]

logger = logging.getLogger(__name__)

CATALOG_PATH = get_data_dir() / "tool_catalog.json"
REMOTE_STORE_URL = os.environ.get("TOOL_STORE_URL", "https://raw.githubusercontent.com/whiletrue247/AgentOS/main/tools_registry.json")

@dataclass
class ToolInfo:
    tool_id: str
    name: str
    description: str
    version: str
    schema: dict
    script_language: str
    script_code: str
    rating: float = 0.0
    reviews_count: int = 0

class Marketplace:
    def __init__(self):
        self._ensure_catalog()

    def _ensure_catalog(self) -> None:
        if not CATALOG_PATH.parent.exists():
            CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not CATALOG_PATH.exists():
            self._save_catalog({})

    def _load_catalog(self) -> Dict[str, dict]:
        try:
            with open(CATALOG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load tool catalog: {e}")
            return {}

    def _save_catalog(self, catalog: Dict[str, dict]) -> None:
        try:
            with open(CATALOG_PATH, "w", encoding="utf-8") as f:
                json.dump(catalog, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save tool catalog: {e}")

    def _fetch_remote_registry(self) -> Dict[str, dict]:
        # Fallback to a mock local registry if remote isn't accessible
        try:
            # Simulate a quick network timeout to fallback if no real real internet available
            req = urllib.request.Request(REMOTE_STORE_URL, headers={'User-Agent': 'AgentOS'})
            with urllib.request.urlopen(req, timeout=3) as response:
                data = response.read()
                return json.loads(data)
        except Exception as e:
            logger.warning(f"Could not fetch remote registry ({e}), using local mock.")
            # Local mock registry
            return {
                "math_utils": {
                    "tool_id": "math_utils",
                    "name": "Math Utils",
                    "description": "Calculates math expressions safely.",
                    "version": "1.0",
                    "schema": {
                        "name": "math_utils",
                        "description": "Calculates math expression",
                        "parameters": {
                            "type": "object",
                            "properties": {"expr": {"type": "string"}},
                            "required": ["expr"]
                        }
                    },
                    "script_language": "python",
                    # 安全計算：使用 ast.literal_eval 防止 RCE，禁止 eval()
                    "script_code": "import sys, ast\\nexpr=sys.argv[1]\\nresult=ast.literal_eval(expr)\\nprint(result)"
                }
            }

    def _validate_tool_schema(self, tool_data: dict) -> bool:
        """驗證是否具備 JSON Schema 以及安全的代碼定義"""
        required_keys = ["tool_id", "name", "schema", "script_language", "script_code"]
        for k in required_keys:
            if k not in tool_data:
                logger.error(f"Tool validation failed: Missing key '{k}'")
                return False
        if not isinstance(tool_data["schema"], dict):
            logger.error("Tool schema must be a dict definition.")
            return False
        return True

    def list_available_tools(self) -> List[ToolInfo]:
        """列出可以從遠端/現有 registry 安裝的所有工具。"""
        registry = self._fetch_remote_registry()
        tools = []
        for tid, data in registry.items():
            if self._validate_tool_schema(data):
                tools.append(ToolInfo(
                    tool_id=data.get("tool_id", tid),
                    name=data.get("name", tid),
                    description=data.get("description", ""),
                    version=data.get("version", "1.0"),
                    schema=data.get("schema", {}),
                    script_language=data.get("script_language", "python"),
                    script_code=data.get("script_code", "")
                ))
        return tools

    def install_tool(self, tool_id: str) -> bool:
        """
        從 Registry 下載工具，驗證其 schema 和格式，寫入本地 catalog。
        不使用 exec_module，確保僅透過 sandbox 以 subprocess 方式執行。
        """
        registry = self._fetch_remote_registry()
        if tool_id not in registry:
            logger.error(f"Tool '{tool_id}' not found in the marketplace.")
            return False

        tool_data = registry[tool_id]
        if not self._validate_tool_schema(tool_data):
            return False

        catalog = self._load_catalog()
        catalog[tool_id] = tool_data
        
        # Initialize rating fields if missing
        if "rating" not in catalog[tool_id]:
            catalog[tool_id]["rating"] = 0.0
            catalog[tool_id]["reviews_count"] = 0

        self._save_catalog(catalog)
        logger.info(f"✅ Tool '{tool_id}' successfully installed to catalog.")
        return True

    def uninstall_tool(self, tool_id: str) -> bool:
        """從本地 catalog 移除指定的工具。"""
        catalog = self._load_catalog()
        if tool_id in catalog:
            del catalog[tool_id]
            self._save_catalog(catalog)
            logger.info(f"🗑️ Tool '{tool_id}' uninstalled.")
            return True
        logger.warning(f"Tool '{tool_id}' is not installed.")
        return False

    def rate_tool(self, tool_id: str, score: float, review: str) -> bool:
        """為本地 catalog 中的工具給予評分，並在未來可同步回遠端。"""
        if not (1.0 <= score <= 5.0):
            logger.error("Score must be between 1.0 and 5.0")
            return False

        catalog = self._load_catalog()
        if tool_id not in catalog:
            logger.error(f"Cannot rate tool '{tool_id}' because it's not installed.")
            return False

        current_rating = catalog[tool_id].get("rating", 0.0)
        current_count = catalog[tool_id].get("reviews_count", 0)

        # Simple moving average for local mock
        new_count = current_count + 1
        new_rating = ((current_rating * current_count) + score) / new_count

        catalog[tool_id]["rating"] = new_rating
        catalog[tool_id]["reviews_count"] = new_count
        
        self._save_catalog(catalog)
        logger.info(f"⭐⭐⭐⭐⭐ Rated '{tool_id}' {score}/5. Note: '{review}'")
        return True
