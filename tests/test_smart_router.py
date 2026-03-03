import sys
import os
import asyncio

# Setup path so it can import from root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config_schema import load_config
from config_schema import ProviderConfig
from importlib import import_module
router_mod = import_module('04_Engine.router')

def test_failover_routing_offline_switch():
    print("\n🚀 Testing Smart Router Failovers: Retry logic and Offline Mode Transition")
    config = load_config()
    config.engine.retry.max_attempts = 2
    
    # 建立 Router 實例
    router = router_mod.SmartRouter(config)
    
    # Simulate network offline failover switch transition...
    router.set_offline_mode(True)
    assert router._offline_mode == True
    
    p_name, model, override_url = router.route("test_agent_fallback", [], [])
    
    print(f"✅ Failover Successfully Assigned Offline Model: {p_name}/{model} (override_url: {override_url})")

if __name__ == "__main__":
    asyncio.run(test_failover_routing_offline_switch())

# --- Added B.2 Multi-model failover testing ---
def test_smart_router_failover_scenarios():
    print("\n🚀 Testing B.2 Smart Router Edge Failover scenarios")
    from config_schema import load_config
    import importlib
    router_mod = importlib.import_module("04_Engine.router")
    
    config = load_config()
    router = router_mod.SmartRouter(config)
    router.set_offline_mode(True)
    
    # test mapping
    p, m, out = router.route("some_missing_agent", [], [])
    assert out is not None
    assert isinstance(p, str)

test_smart_router_failover_scenarios()
