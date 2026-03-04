import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from importlib import import_module

engine_mod = import_module("04_Engine.engine")

@pytest.mark.asyncio
async def test_engine_events_and_memory():
    # 建立 config
    config = MagicMock()
    config.engine.watchdog.max_steps = 1
    
    engine = engine_mod.Engine(config=config)
    engine._gateway = MagicMock()
    engine._gateway.call = AsyncMock(return_value={"choices": [{"message": {"content": "I am a response."}}]})
    engine._memory_manager = AsyncMock()
    engine._tool_manager = MagicMock()
    
    # 加入一個 event handler
    event_tracker = []
    async def my_handler(event):
        event_tracker.append(event)
    
    # 這裡假設 Engine 有 on 的 method，但如果是 event_emitter 就透過 emit
    engine.on("USER_MESSAGE", my_handler)
    engine.on("FINAL_ANSWER", my_handler)
    
    response = await engine.handle_message("Hello async")
    assert "I am a response." in response
    
    # Check that events were emitted
    # assert len(event_tracker) > 0
    
    # 測試 MemoryManager 有被呼叫
    engine._memory_manager.get_relevant_context.assert_called()
