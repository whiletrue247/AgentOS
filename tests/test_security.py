"""
tests/test_security.py
======================
Verification of SubprocessSandbox hardening logic.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import importlib.util

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

sandbox_mod = load_module("sandbox_subprocess", os.path.abspath("03_Tool_System/sandbox_subprocess.py"))
SubprocessSandbox = sandbox_mod.SubprocessSandbox

@pytest.fixture
def sandbox():
    # Make sure we don't accidentally load Zero Trust which requires interactive input
    sb = SubprocessSandbox()
    sb._interceptor = None 
    return sb


@pytest.mark.asyncio
async def test_static_block(sandbox):
    """驗證 rm -rf / 直接被靜態攔截"""
    result = await sandbox.execute("rm -rf /")
    assert result.success is False
    assert "Blocked by static security filter" in result.error


def test_env_stripping(sandbox):
    """驗證 _build_secure_env() 移除了 API KEY"""
    # 確保原本環境有該 key，做測試
    os.environ["OPENAI_API_KEY"] = "sk-fake123"
    try:
        env = sandbox._build_secure_env(network_allowed=True)
        assert "OPENAI_API_KEY" not in env
    finally:
        os.environ.pop("OPENAI_API_KEY", None)


def test_path_sanitization(sandbox):
    """驗證 PATH 中 `/sbin` 被移除"""
    os.environ["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    try:
        env = sandbox._build_secure_env(network_allowed=True)
        assert "sbin" not in env.get("PATH", "")
        assert "/bin" in env.get("PATH", "")
    finally:
        pass  # path will be restored or won't break things


def test_network_deny(sandbox):
    """驗證 network_allowed=False 時設定了 proxy 環境變數"""
    env = sandbox._build_secure_env(network_allowed=False)
    assert env.get("http_proxy") == "http://127.0.0.1:1"
    assert env.get("HTTPS_PROXY") == "http://127.0.0.1:1"
    assert "127.0.0.1" in env.get("NO_PROXY", "")


@pytest.mark.asyncio
async def test_timeout_kills_process(sandbox):
    """啟動 `sleep 999`，設 timeout=1s，驗證被 kill"""
    # Windows doesn't have bash sleep in standard Python usually, but assumed Unix 
    script = "import time\ntime.sleep(999)"
    result = await sandbox.execute(script, language="python", timeout_seconds=1)
    
    assert result.success is False
    assert "Timeout after" in result.error
    assert "killed" in result.error
