import pytest
from unittest.mock import AsyncMock, MagicMock
from importlib import import_module

engine_mod = import_module("04_Engine.engine")
router_mod = import_module("04_Engine.router")

@pytest.fixture
def mock_gateway():
    gateway = MagicMock()
    gateway.call = AsyncMock(return_value={"choices": [{"message": {"content": "I am a helpful agent."}}]})
    return gateway

@pytest.fixture
def mock_memory_manager():
    mm = AsyncMock()
    mm.retrieve_context.return_value = []
    return mm

@pytest.fixture
def mock_tool_manager():
    tm = AsyncMock()
    tm.get_tools_schema.return_value = []
    tm.execute_tool.return_value = "Tool result"
    return tm

@pytest.mark.asyncio
async def test_engine_chat(mock_gateway, mock_memory_manager, mock_tool_manager):
    config = MagicMock()
    config.engine.watchdog.max_steps = 10
    engine = engine_mod.Engine(config=config)
    engine._gateway = mock_gateway
    engine._memory_manager = mock_memory_manager
    engine._tool_manager = mock_tool_manager
    
    # 測試 handle_message
    response = await engine.handle_message("Hello async")
    assert "I am a helpful agent." in response
    mock_gateway.call.assert_called()

@pytest.mark.asyncio
async def test_engine_auto_execute_tool(mock_gateway, mock_memory_manager, mock_tool_manager):
    config = MagicMock()
    config.engine.watchdog.max_steps = 10
    engine = engine_mod.Engine(config=config)
    engine._gateway = mock_gateway
    engine._memory_manager = mock_memory_manager
    engine._tool_manager = mock_tool_manager
    
    # 第一輪回傳要呼叫工具，第二輪結束
    mock_gateway.call.side_effect = [
        {"choices": [{"message": {
            "content": "", "tool_calls": [{"id": "call_1", "function": {"name": "test_tool", "arguments": "{}"}}]
        }}]},
        {"choices": [{"message": {"content": "Final Answer"}}]}
    ]
    
    response = await engine.handle_message("Use tool")
    assert "Final Answer" in response
    # mock_tool_manager.execute_tool.assert_called_once_with("test_tool", "{}")
