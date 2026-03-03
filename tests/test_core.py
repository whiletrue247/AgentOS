"""
tests/test_core.py
==================
Unit tests for core modules: NPU Detector, Smart Router, Zero Trust, and Cost Guard.
"""

import sys
import os

# Add parent directory to path so we can import internal modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import importlib.util

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

npu_detector_mod = load_module("npu_detector", os.path.abspath("04_Engine/npu_detector.py"))
router_mod = load_module("router", os.path.abspath("04_Engine/router.py"))
zero_trust_mod = load_module("zero_trust", os.path.abspath("04_Engine/zero_trust.py"))

NPUDetector = getattr(npu_detector_mod, "NPUDetector", None)
SmartRouter = router_mod.SmartRouter
ZeroTrustInterceptor = zero_trust_mod.ZeroTrustInterceptor


class MockConfig:
    class GatewayConfig:
        class ProviderInfo:
            def __init__(self, name, base_url, api_key, models):
                self.name = name
                self.base_url = base_url
                self.api_key = api_key
                self.models = models

        providers = [
            ProviderInfo("ollama", "http://localhost:11434", None, ["llama3.2"]),
            ProviderInfo("openai", None, "sk-123", ["gpt-4o", "gpt-3.5-turbo"])
        ]
        agents = {"default": "openai/gpt-4o"}

    class BudgetConfig:
        daily_limit_m = 1.0

    gateway = GatewayConfig()
    budget = BudgetConfig()


def test_npu_detector():
    """驗證 HardwareProfile 回傳 + recommended_backend 有值"""
    profile = NPUDetector.detect()
    assert profile is not None
    assert profile.recommended_local_backend in ["cpu", "mps", "cuda", "rocm", "xpu", "arm-compute", "coreml", "tensorrt", "directml", "openvino"]
    assert profile.cpu_arch != ""
    assert profile.os_name != ""


def test_router_offline_mode():
    """設定 offline → 確認只路由到本地 provider"""
    router = SmartRouter(config=MockConfig())
    # 設定能力以便 fallback 尋找
    router.capabilities = {"roles": {"fallback_offline": ["ollama/llama3.2"]}}
    
    router.set_offline_mode(True)
    prov, mod, url = router.route("default", messages=[{"role": "user", "content": "hi"}])
    
    assert prov == "ollama"
    assert mod == "llama3.2"
    assert url == "http://localhost:11434"


def test_router_complexity():
    """測試 basic/coding/complex 判定邏輯"""
    router = SmartRouter(config=MockConfig())
    
    # 1. Basic
    res_basic = router.determine_complexity(messages=[{"role": "user", "content": "hi"}], tools=[])
    assert res_basic == "basic"
    
    # 2. Coding (from system prompt keyword)
    res_coding = router.determine_complexity(
        messages=[{"role": "system", "content": "You are a Python developer"}, {"role": "user", "content": "write code"}],
        tools=[]
    )
    assert res_coding == "coding"
    
    # 3. Complex (tool count >= 5)
    tools_complex = [{"name": f"tool_{i}"} for i in range(5)]
    res_complex = router.determine_complexity(messages=[], tools=tools_complex)
    assert res_complex == "complex"


def test_zero_trust_block(monkeypatch):
    """測試 high risk payload (如 rm -rf /) 被攔截"""
    interceptor = ZeroTrustInterceptor()
    
    payload = "sudo rm -rf /"
    
    # 攔截標準輸入以免需要人類回覆，強制回傳 cancel
    def mock_notify(role, payload_text):
        return 'cancel'
    
    monkeypatch.setattr(interceptor, "_notify_human_supervisor", mock_notify)
    
    is_allowed, reason = interceptor.verify_action("default", "shell", payload)
    assert is_allowed is False
    assert "Execution Denied" in reason


def test_zero_trust_allow(monkeypatch):
    """測試正常指令通過"""
    interceptor = ZeroTrustInterceptor()
    payload = "ls -la"
    
    # 給予充足權限
    interceptor.config = {
        "roles": {
            "default": {
                "can_execute_shell": True
            }
        },
        "policies": {
            "destructive_commands_regex": [r"rm\s+-rf\s+/"]
        }
    }
    
    is_allowed, reason = interceptor.verify_action("default", "shell", payload)
    assert is_allowed is True
    assert reason == "Passed"


def test_cost_guard():
    """測試預算超支時 get_cheaper_alternative 回傳值"""
    router = SmartRouter(config=MockConfig())
    router.capabilities = {"roles": {"writer": ["openai/gpt-3.5-turbo"]}}
    
    # Session cost 還沒接近 daily limit
    router._session_cost_usd = 0.5
    assert router.get_cheaper_alternative("gpt-4o") is None
    
    # Session cost 接近 daily limit (0.8+)
    router._session_cost_usd = 0.9
    alt = router.get_cheaper_alternative("gpt-4o")
    assert alt == "openai/gpt-3.5-turbo"
