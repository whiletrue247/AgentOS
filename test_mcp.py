import asyncio
import logging
import sys
import os

from config_schema import AgentOSConfig, MCPConfig, MCPServerConfig
from paths import get_catalog_path

# Add project root to path so we can import modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from importlib import import_module
catalog_mod = import_module('03_Tool_System.catalog')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MCP_TEST")

async def test_mcp():
    config = AgentOSConfig()
    config.mcp.servers = {
        "sqlite": MCPServerConfig(
            command="./.venv_mcp/bin/mcp-server-sqlite",
            args=["--db-path", "test.db"]
        ),
        "time": MCPServerConfig(
            command="./.venv_mcp/bin/mcp-server-time",
            args=[]
        )
    }
    
    logger.info("初始化 ToolCatalog 並連線 MCP Servers...")
    catalog = catalog_mod.ToolCatalog(config=config, catalog_path="data/test_catalog.json")
    await catalog.init_mcp_servers()
    
    print("\n" + "="*50)
    print("✨ 已載入的工具 ✨")
    print("="*50)
    for t in catalog.get_all_tools():
        print(f"🔧 [{t.mcp_server or 'local'}] {t.name}\n   {t.description}")
        if t.mcp_server:
            print(f"   參數 Schema: {t.parameters.get('properties', {}).keys()}")
        print("-" * 50)
        
    print("\n" + "="*50)
    print("🚀 測試執行 `time` MCP Server 的 get_current_time 工具")
    print("="*50)
    try:
        time_client = catalog.mcp_clients["time"]
        time_res = await time_client.call_tool("get_current_time", {"timezone": "Asia/Taipei"})
        print(f"✅ 成功取得時間: {time_res}")
    except Exception as e:
        print(f"❌ 測試失敗: {e}")

    await catalog.shutdown()

if __name__ == "__main__":
    asyncio.run(test_mcp())
