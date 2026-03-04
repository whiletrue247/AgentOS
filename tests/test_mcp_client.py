import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from importlib import import_module

mcp_mod = import_module("03_Tool_System.mcp_client")
@pytest.fixture
def temp_mcp_client():
    from config_schema import MCPServerConfig
    cfg = MCPServerConfig(command="node", args=["server.js"])
    client = mcp_mod.MCPClient("test_mcp", cfg)
    return client

@pytest.mark.asyncio
async def test_mcp_client_lifecycle(temp_mcp_client, monkeypatch):
    """測試 MCP Client 的啟動, 工具掃描, 與停止流程"""
    # 模擬 subprocess 的建立, 確保不實際執行 node
    mock_process = AsyncMock()
    mock_process.returncode = None
    mock_process.stdin = MagicMock()
    mock_process.stdin.write = MagicMock()
    mock_process.stdin.drain = AsyncMock()
    mock_process.stdout = AsyncMock()
    # Mocking real lines to read
    mock_process.stdout.readline.side_effect = [
        b'{"jsonrpc":"2.0", "id": 1, "result": {"tools": [{"name":"mock_tool"}]}}\n',
        b'' # EOF
    ]
    mock_process.kill = MagicMock()
    mock_process.wait = AsyncMock()
    
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        
        # mock stdin write to be a normal function or properly await it
        mock_process.stdin.write = MagicMock()
        mock_process.stdin.drain = AsyncMock()
        
        # 測試啟動
        await temp_mcp_client.start()
        assert temp_mcp_client._process is not None
        mock_exec.assert_called_once()
        
        # 模擬 _send_request (跳過真實寫入)
        # 用 mock 直接取代, 因為 readline mock 也只能跑一次
        temp_mcp_client._send_request = AsyncMock(return_value={"tools": [{"name": "mock_tool"}]})
        
        # 測試載入工具
        tools = await temp_mcp_client.get_tools()
        assert len(tools) == 1
        assert tools[0].name == "test_mcp_mock_tool"
        
        # 測試呼叫工具
        temp_mcp_client._send_request.return_value = {"content": [{"type": "text", "text": "Success"}]}
        result = await temp_mcp_client.call_tool("test_mcp_mock_tool", {"arg1": "test"})
        assert result == "Success"
        
        # 測試停止
        await temp_mcp_client.stop()
        mock_process.terminate.assert_called_once()
