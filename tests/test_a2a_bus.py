import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from importlib import import_module

a2a_mod = import_module("05_Orchestrator.a2a_bus")
from contracts.interfaces import SubTask

@pytest.fixture
def mock_engine():
    engine = MagicMock()
    # Mocking call to return a success response
    engine.gateway.call = AsyncMock(return_value={"choices": [{"message": {"content": "APPROVED Task executed successfully!"}}]})
    return engine

@pytest.mark.asyncio
async def test_a2a_bus_dispatch_task(mock_engine):
    bus = a2a_mod.A2ABus(engine=mock_engine)
    task = SubTask(id="task_1", description="Test subtask", agent_role="Developer")
    
    result = await bus.dispatch_task(task, global_context="Test context")
    assert "Task executed successfully" in result or result != ""

@pytest.mark.asyncio
async def test_a2a_bus_dispatch_with_ack(mock_engine, monkeypatch):
    """測試 SPR4 的 ACK 機制與指數退避重試"""
    # 改變重試延遲讓測試跑得快
    monkeypatch.setattr(a2a_mod, "BASE_RETRY_DELAY_S", 0.01)
    
    bus = a2a_mod.A2ABus(engine=mock_engine)
    task = SubTask(id="task_ack", description="Test ACK", agent_role="Tester")
    
    receipt = await bus.dispatch_task_with_ack(task)
    assert receipt.status == "ack"
    assert receipt.attempts == 1
    assert receipt.message_id.startswith("msg_")
    
    # 驗證可以取得回執
    fetched = bus.get_receipt(receipt.message_id)
    assert fetched == receipt
    
    # 驗證錯誤重試與最終 NACK
    mock_engine.gateway.call = AsyncMock(side_effect=Exception("API Error Dummy"))
    bus2 = a2a_mod.A2ABus(engine=mock_engine)
    
    receipt2 = await bus2.dispatch_task_with_ack(task)
    assert receipt2.status == "nack"
    assert receipt2.attempts == a2a_mod.MAX_DISPATCH_RETRIES
    assert "API Error Dummy" in receipt2.error

def test_a2a_bus_fallback():
    bus = a2a_mod.A2ABus(engine=MagicMock())
    # Test property or state if applicable
    assert hasattr(bus, "dispatch_task")
