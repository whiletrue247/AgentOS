import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from importlib import import_module
import asyncio

a2a_mod = import_module("05_Orchestrator.a2a_bus")
from contracts.interfaces import SubTask

@pytest.fixture
def mock_engine():
    engine = MagicMock()
    # Mocking call to return a success response
    engine.gateway.call = AsyncMock(return_value={"choices": [{"message": {"content": "APPROVED extra"}}]})
    return engine

@pytest.mark.asyncio
async def test_a2a_bus_spawn_sub_swarm(mock_engine):
    bus = a2a_mod.A2ABus(engine=mock_engine, depth=1)
    
    # Mock some basic agent response format to pass the spawn behavior
    task1 = SubTask(id="sub1", description="t1", agent_role="coder")
    results = await bus.spawn_sub_swarm([task1], "objective")
    assert type(results) is dict

@pytest.mark.asyncio
async def test_a2a_bus_get_receipt():
    bus = a2a_mod.A2ABus(engine=MagicMock())
    bus._receipts["msg_1"] = "some_receipt"
    assert bus.get_receipt("msg_1") == "some_receipt"
    assert "msg_1" in bus.get_all_receipts()

