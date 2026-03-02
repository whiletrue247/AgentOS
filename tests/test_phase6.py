import pytest
import os
import sys
import importlib.util

# 動態加載測試，因為目錄名稱開頭為數字
def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

os_hook_mod = load_module("os_hook", os.path.abspath("09_OS_Integration/os_hook.py"))
daily_feedback_mod = load_module("daily_feedback", os.path.abspath("04_Engine/daily_feedback.py"))
store_manager_mod = load_module("store_manager", os.path.abspath("10_Marketplace/store_manager.py"))
handoff_manager_mod = load_module("handoff_manager", os.path.abspath("11_Sync_Handoff/handoff_manager.py"))

@pytest.mark.asyncio
async def test_os_hook_factory():
    hook = os_hook_mod.get_native_hook()
    assert isinstance(hook, os_hook_mod.BaseOSHook)
    # 測試基本介面
    window = await hook.get_active_window()
    assert isinstance(window, dict)
    
@pytest.mark.asyncio
async def test_daily_feedback():
    # 測試輸出 jsonl
    export_path = "tests/test_feedback.jsonl"
    feedback_loop = daily_feedback_mod.DailyFeedbackLoop(engine=None, audit_provider=None, export_path=export_path)
    
    await feedback_loop.run_daily_evaluation("2026-03-02")
    
    assert os.path.exists(export_path)
    with open(export_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) == 2 # 根據 mock 有兩個案例
        assert "next time verify element" in lines[1].lower()
    
    os.remove(export_path)

def test_marketplace():
    wallet = store_manager_mod.MTokenWallet(initial_balance=10.0)
    store = store_manager_mod.AgentMarketplace(wallet)
    
    items = store.browse()
    assert len(items) == 2
    
    # 嘗試買第一個 (2.5) => 成功
    payload = store.install_item(items[0]['item_id'])
    assert payload is not None
    assert wallet.balance == 7.5
    
    # 嘗試買另一個 (5.0) => 成功
    payload_2 = store.install_item(items[1]['item_id'])
    assert payload_2 is not None
    assert wallet.balance == 2.5
    
    # 餘額不足買第二次 (5.0, 但剩下 2.5)
    payload_3 = store.install_item(items[1]['item_id'])
    assert payload_3 is None
    assert wallet.balance == 2.5

def test_handoff_manager():
    manager = handoff_manager_mod.HandoffManager()
    
    # 模擬任務狀態
    mock_state = {"current_node": "planning", "messages": [{"role": "user", "content": "Help me"}]}
    task_id = "task-alpha-123"
    
    # 輸出加密的 URI
    uri = manager.export_session_state(task_id, mock_state)
    assert uri.startswith("agentos://handoff?payload=")
    
    # 解密導入 URI
    restored_state = manager.import_session_state(uri)
    assert restored_state is not None
    assert restored_state["current_node"] == "planning"
    assert restored_state["messages"][0]["content"] == "Help me"
    
    # 測試壞掉的 URI
    assert manager.import_session_state("agentos://baduri") is None
