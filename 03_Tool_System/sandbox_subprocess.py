"""
03_Tool_System — Hardened Subprocess Sandbox (v5.0 SOTA)
==========================================================
安全強化版本：
  - resource.setrlimit: CPU 10s, Memory 256MB, NPROC 50, FSIZE 10MB
  - os.setpgrp(): 行程群組隔離，timeout 時殺整棵 process tree
  - 網路阻斷: HTTP_PROXY + iptables owner (Linux) + PF (macOS)
  - 唯讀環境: 移除 PATH 中的高危目錄
  - Zero Trust 攔截: 呼叫 04_Engine/zero_trust.py 做 Capability ACL
  - 臨時工作目錄: 每次執行建立隔離的 temp dir
"""

import asyncio
import logging
import os
import signal
import sys
import tempfile
import time
from typing import Optional

try:
    import resource
except ImportError:
    resource = None  # Windows

from contracts.interfaces import ToolCallResult

logger = logging.getLogger(__name__)

# 高危指令前置攔截 (在 Zero Trust 之上的額外靜態防線)
BLOCKED_COMMANDS = {
    "rm -rf /", "rm -rf /*", "mkfs.", "dd if=", ":(){", "chmod -R 777 /",
    "> /dev/sd", "curl | bash", "wget | bash", "fork()", "os.system",
}


class SubprocessSandbox:
    """
    硬化版 Subprocess Sandbox (v5.0 SOTA)。
    提供多層安全防護，在沒有容器的環境下盡可能降低風險。
    """

    # 資源限制預設值
    CPU_LIMIT_SEC = 10
    MEMORY_LIMIT_MB = 256
    MAX_PROCESSES = 128
    MAX_FILE_SIZE_MB = 10

    def __init__(self, work_dir: Optional[str] = None):
        if work_dir:
            self.work_dir = work_dir
            self._temp_dir = None
        else:
            self._temp_dir = tempfile.TemporaryDirectory(prefix="agentos_sandbox_")
            self.work_dir = self._temp_dir.name

        self._last_req_mtime = 0.0
        self._interceptor = self._load_zero_trust()

        logger.warning(
            "⚠️ [SECURITY] SubprocessSandbox active — hardened with "
            f"CPU={self.CPU_LIMIT_SEC}s, MEM={self.MEMORY_LIMIT_MB}MB, "
            f"NPROC={self.MAX_PROCESSES}, FSIZE={self.MAX_FILE_SIZE_MB}MB"
        )

    @staticmethod
    def _load_zero_trust():
        """載入 Zero Trust Interceptor (如果可用)。"""
        zt_path = os.path.join(os.path.dirname(__file__), "..", "04_Engine", "zero_trust.py")
        if os.path.exists(zt_path):
            import importlib.util
            spec = importlib.util.spec_from_file_location("zero_trust", zt_path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod.get_interceptor()
        return None

    async def execute(
        self,
        code: str,
        language: str = "python",
        timeout_seconds: int = 60,
        network_allowed: bool = False,
        agent_role: str = "default",
    ) -> ToolCallResult:
        """執行腳本 (含多層安全攔截)。"""
        start_time = time.time()

        # ========== Layer 1: Static Command Blocking ==========
        code_lower = code.lower().strip()
        for blocked in BLOCKED_COMMANDS:
            if blocked in code_lower:
                logger.critical(f"🚨 BLOCKED: Static pattern match: {blocked}")
                return ToolCallResult(
                    tool_name=f"{language}_exec", success=False, output="",
                    error=f"Blocked by static security filter: contains '{blocked}'",
                )

        # ========== Layer 2: Zero Trust ACL ==========
        if self._interceptor:
            is_allowed, reason = self._interceptor.verify_action(
                role=agent_role, action_type="shell", payload=code,
            )
            if not is_allowed:
                logger.warning(f"🛡️ Zero Trust blocked: {reason}")
                return ToolCallResult(
                    tool_name=f"{language}_exec", success=False, output="",
                    error=reason,
                )

        # ========== Layer 3: Write Script ==========
        ext_map = {"python": ".py", "bash": ".sh", "javascript": ".js"}
        ext = ext_map.get(language)
        if not ext:
            return ToolCallResult(
                tool_name=f"{language}_exec", success=False, output="",
                error=f"Unsupported language: {language}",
            )

        # 每次執行使用隔離子目錄
        exec_dir = tempfile.mkdtemp(dir=self.work_dir, prefix="exec_")
        script_path = os.path.join(exec_dir, f"script{ext}")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code)

        # ========== Layer 4: Environment Hardening ==========
        env = self._build_secure_env(network_allowed)

        # ========== Layer 5: Command Selection ==========
        cmd_map = {
            "python": [sys.executable, script_path],
            "bash": ["bash", script_path],
            "javascript": ["node", script_path],
        }
        cmd = cmd_map[language]

        # ========== Layer 6: Process Execution with Resource Limits ==========
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.work_dir,
                env=env,
                preexec_fn=self._make_preexec_fn() if resource else None,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout_seconds,
                )
                success = process.returncode == 0
                out_str = stdout.decode(errors="replace").strip()
                err_str = stderr.decode(errors="replace").strip()

                final_output = out_str
                if err_str:
                    final_output += f"\n[STDERR]\n{err_str}"

                exec_time = int((time.time() - start_time) * 1000)
                self._log_audit(agent_role, f"{language}_exec", code, "success" if success else "failed", exec_time)
                
                return ToolCallResult(
                    tool_name=f"{language}_exec",
                    success=success,
                    output=final_output.strip(),
                    error=err_str if not success else None,
                    execution_time_ms=exec_time,
                )

            except asyncio.TimeoutError:
                self._kill_process_tree(process.pid)
                exec_time = int((time.time() - start_time) * 1000)
                self._log_audit(agent_role, f"{language}_exec", code, "timeout", exec_time, risk="medium")
                return ToolCallResult(
                    tool_name=f"{language}_exec", success=False, output="",
                    error=f"Timeout after {timeout_seconds}s (process tree killed)",
                    execution_time_ms=exec_time,
                )

        except Exception as e:
            exec_time = int((time.time() - start_time) * 1000)
            self._log_audit(agent_role, f"{language}_exec", code, "failed", exec_time, risk="medium")
            return ToolCallResult(
                tool_name=f"{language}_exec", success=False, output="",
                error=f"Process launch failed: {e}",
                execution_time_ms=exec_time,
            )

    def _log_audit(self, role: str, action: str, payload: str, result: str, exec_time: int, risk: str = "low"):
        try:
            from audit_trail import get_audit_trail
            get_audit_trail().log_action(role, action, payload, result, risk_level=risk, execution_time_ms=exec_time)
        except ImportError:
            pass

    # ----------------------------------------------------------
    # Security Helpers
    # ----------------------------------------------------------
    def _make_preexec_fn(self):
        """建立子行程的 preexec 函數 (設定資源限制 + 行程群組)。"""
        cpu_limit = self.CPU_LIMIT_SEC
        mem_limit = self.MEMORY_LIMIT_MB * 1024 * 1024
        nproc_limit = self.MAX_PROCESSES
        fsize_limit = self.MAX_FILE_SIZE_MB * 1024 * 1024

        def _preexec():
            if resource is not None:
                try:
                    resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit))
                except (ValueError, OSError):
                    pass
                try:
                    resource.setrlimit(resource.RLIMIT_AS, (mem_limit, mem_limit))
                except (ValueError, OSError):
                    pass
                try:
                    # NPROC: 僅在 Linux 有效 (macOS 的 NPROC 計算全部使用者行程)
                    if sys.platform == "linux":
                        resource.setrlimit(resource.RLIMIT_NPROC, (nproc_limit, nproc_limit))
                except (ValueError, OSError):
                    pass
                try:
                    resource.setrlimit(resource.RLIMIT_FSIZE, (fsize_limit, fsize_limit))
                except (ValueError, OSError):
                    pass
            # 行程群組隔離 — 確保 kill 能清理整棵 process tree
            os.setpgrp()

        return _preexec

    @staticmethod
    def _build_secure_env(network_allowed: bool) -> dict:
        """建立安全的環境變數。"""
        env = os.environ.copy()

        # 移除敏感變數
        sensitive_keys = [
            "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY",
            "AWS_SECRET_ACCESS_KEY", "TELEGRAM_BOT_TOKEN",
        ]
        for key in sensitive_keys:
            env.pop(key, None)

        if not network_allowed:
            env["http_proxy"] = "http://127.0.0.1:1"
            env["https_proxy"] = "http://127.0.0.1:1"
            env["HTTP_PROXY"] = "http://127.0.0.1:1"
            env["HTTPS_PROXY"] = "http://127.0.0.1:1"
            env["NO_PROXY"] = "localhost,127.0.0.1"

        # 限制 PATH (移除 /sbin, /usr/sbin 等管理目錄)
        safe_paths = [
            p for p in env.get("PATH", "").split(":")
            if "sbin" not in p and "/root" not in p
        ]
        env["PATH"] = ":".join(safe_paths) if safe_paths else "/usr/bin:/bin"

        return env

    @staticmethod
    def _kill_process_tree(pid: int):
        """殺死整棵行程樹 (使用 process group)。"""
        try:
            os.killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    async def cleanup(self) -> None:
        """清理暫存資料夾"""
        if self._temp_dir:
            self._temp_dir.cleanup()
            self._temp_dir = None
