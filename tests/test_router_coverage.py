import pytest
from config_schema import load_config
import importlib

def test_smart_router_failover_scenarios():
    router_mod = importlib.import_module("04_Engine.router")
    
    config = load_config()
    router = router_mod.SmartRouter(config)
    router.set_offline_mode(True)
    
    # test offline routing raises value error as expected
    with pytest.raises(ValueError, match="No local provider available for offline mode."):
        p, m, out = router.route("some_missing_agent", [], [])
        
    router.set_offline_mode(False)
    
    # test fallback logic with an unknown agent
    p, m, out = router.route("some_missing_agent", ["unknown"], [])
    assert out is not None

