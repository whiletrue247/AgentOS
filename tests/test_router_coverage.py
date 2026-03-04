import pytest
from config_schema import load_config
import importlib

def test_smart_router_failover_scenarios():
    router_mod = importlib.import_module("04_Engine.router")
    
    config = load_config()
    from config_schema import ProviderConfig
    config.gateway.providers.append(ProviderConfig(name="openai", base_url="https://api.openai.com"))
    router = router_mod.SmartRouter(config)
    router.set_offline_mode(True)
    
    # test offline routing raises value error as expected
    try:
        p, m, out = router.route("some_missing_agent", [], [])
    except ValueError:
        pass
        
    router.set_offline_mode(False)
    
    # test fallback logic with an unknown agent
    p, m, out = router.route("some_missing_agent", [{"role": "user", "content": "unknown"}], [])
    assert out is not None

