"""
單元測試 — SandboxManager._scan_code_safety()
==============================================
測試代碼安全掃描的 11 種危險模式偵測及安全代碼放行。
"""

import pytest
import sys
import os

# 確保專案根目錄在 sys.path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "03_Tool_System"))

from sandbox import SandboxManager  # noqa: E402


# ============================================================
# Helper
# ============================================================

def scan(code: str, language: str = "python"):
    """呼叫 _scan_code_safety 並回傳結果"""
    return SandboxManager._scan_code_safety(code, language)


# ============================================================
# 安全代碼應通過
# ============================================================

class TestSafeCode:
    def test_simple_print(self):
        assert scan("print('hello world')") is None

    def test_math_code(self):
        assert scan("import math\nresult = math.sqrt(16)\nprint(result)") is None

    def test_file_read_safe(self):
        assert scan("with open('data.txt') as f:\n    print(f.read())") is None

    def test_javascript_bypasses_scan(self):
        # JavaScript 不進行 Python/bash 模式掃描
        assert scan("os.environ['SECRET']", language="javascript") is None

    def test_empty_code(self):
        assert scan("") is None


# ============================================================
# 危險模式應被攔截
# ============================================================

class TestDangerousPatterns:
    def test_os_environ(self):
        result = scan("import os\nprint(os.environ['API_KEY'])")
        assert result is not None
        assert not result.success
        assert "os.environ" in result.error

    def test_os_getenv(self):
        result = scan("import os\nkey = os.getenv('SECRET')")
        assert result is not None
        assert not result.success

    def test_subprocess_run(self):
        result = scan("import subprocess\nsubprocess.run(['rm', '-rf', '/'])")
        assert result is not None
        assert not result.success
        assert "subprocess" in result.error

    def test_subprocess_popen(self):
        result = scan("import subprocess\np = subprocess.Popen(['ls'])")
        assert result is not None
        assert not result.success

    def test_os_system(self):
        result = scan("import os\nos.system('rm -rf /')")
        assert result is not None
        assert not result.success

    def test_os_popen(self):
        result = scan("import os\nos.popen('cat /etc/passwd')")
        assert result is not None
        assert not result.success

    def test_socket_creation(self):
        result = scan("import socket\ns = socket.socket(socket.AF_INET, socket.SOCK_STREAM)")
        assert result is not None
        assert not result.success
        assert "socket" in result.error

    def test_ctypes_cdll(self):
        result = scan("import ctypes\nlib = ctypes.cdll.LoadLibrary('libc.so.6')")
        assert result is not None
        assert not result.success

    def test_importlib_exec_module(self):
        result = scan("import importlib\nspec = importlib.util.spec_from_file_location('m', 'evil.py')\nimportlib.util.module_from_spec(spec)\nspec.loader.exec_module(mod)")
        assert result is not None
        assert not result.success
        assert "RCE" in result.error

    def test_proc_filesystem(self):
        result = scan("with open('/proc/self/environ') as f:\n    print(f.read())")
        assert result is not None
        assert not result.success

    def test_etc_shadow(self):
        result = scan("with open('/etc/shadow') as f:\n    pass")
        assert result is not None
        assert not result.success

    def test_shutil_rmtree_root(self):
        result = scan("import shutil\nshutil.rmtree('/')")
        assert result is not None
        assert not result.success

    def test_os_fork(self):
        result = scan("import os\nwhile True:\n    os.fork()")
        assert result is not None
        assert not result.success
        assert "fork" in result.error

    def test_bash_dangerous(self):
        result = scan("os.system('whoami')", language="bash")
        assert result is not None
        assert not result.success


# ============================================================
# 代碼長度限制
# ============================================================

class TestCodeLength:
    def test_within_limit(self):
        code = "x = 1\n" * 1000  # ~6KB
        assert scan(code) is None

    def test_exceeds_limit(self):
        code = "x = 1\n" * 20000  # ~120KB
        result = scan(code)
        assert result is not None
        assert not result.success
        assert "length" in result.error.lower()
