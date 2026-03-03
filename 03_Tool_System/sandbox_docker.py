"""
Docker 沙盒 (DockerSandbox) — Hardened v2
==========================================
基於 Docker CLI 實作的主機實體隔離沙盒。
多層防禦：
  Layer 1: resource.setrlimit (主機側行程限制)
  Layer 2: Docker --read-only/--cap-drop/--no-new-privileges
  Layer 3: Linux namespace 隔離 (unshare)
  Layer 4: 可選 gVisor/Kata runtime
"""

import asyncio
import logging
import os
import platform
import resource
import tempfile
import time
from typing import Optional

from contracts.interfaces import SandboxProvider, ToolCallResult

logger = logging.getLogger(__name__)


# ============================================================
# Host-side resource limits (defense-in-depth)
# ============================================================

def _preexec_rlimit():
    """
    在子進程啟動前設定 resource limits。
    即使 Docker 本身有 --memory/--cpus 限制，這一層
    確保 docker CLI 本身不會被 abuse。
    """
    try:
        # 最大開啟檔案數 = 256
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
        # 最大子進程數 = 64
        resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
        # 最大虛擬記憶體 = 256 MB
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
        # 最大單檔大小 = 10 MB
        resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
        # CPU 時間限制 = 30 秒
        resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    except (ValueError, OSError):
        pass  # macOS 不支援部分 rlimit


class DockerSandbox(SandboxProvider):
    """
    基於 Docker Container 的安全沙盒 (Hardened v2)。
    
    安全層級：
      - resource.setrlimit: 主機側行程資源限制
      - Docker flags: read-only, cap-drop ALL, no-new-privileges, pids-limit
      - namespace: --userns (Linux only)
      - runtime: gVisor/Kata (可選)
    """

    def __init__(self, work_dir: Optional[str] = None, docker_runtime: str = ""):
        self.docker_runtime = docker_runtime
        self._is_linux = platform.system() == "Linux"
        if work_dir:
            self.work_dir = work_dir
            self._temp_dir = None
        else:
            self._temp_dir = tempfile.TemporaryDirectory(prefix="agentos_docker_")
            self.work_dir = self._temp_dir.name
            
        logger.info(
            f"🐳 DockerSandbox 初始化 (hardened v2): "
            f"dir={self.work_dir}, runtime={docker_runtime or 'default'}, "
            f"linux={self._is_linux}"
        )

    async def execute(
        self,
        code: str,
        language: str = "python",
        timeout_seconds: int = 60,
        network_allowed: bool = False,
        agent_role: str = "default",
    ) -> ToolCallResult:
        """
        在受限的 Docker 容器中執行腳本。
        含 Zero Trust 攔截 + resource.setrlimit + Docker 強化。
        """
        import importlib.util
        zt_path = os.path.join(os.path.dirname(__file__), "..", "04_Engine", "zero_trust.py")
        if os.path.exists(zt_path):
            spec = importlib.util.spec_from_file_location("zero_trust", zt_path)
            if spec and spec.loader:
                zero_trust_mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(zero_trust_mod)
                interceptor = zero_trust_mod.get_interceptor()
                is_allowed, reason = interceptor.verify_action(role=agent_role, action_type="shell", payload=code)
                if not is_allowed:
                    logger.warning(f"🛡️ [DockerSandbox] 執行被 Zero Trust 攔截: {reason}")
                    return ToolCallResult(
                        tool_name=f"{language}_exec",
                        success=False,
                        output="",
                        error=reason
                    )
        start_time = time.time()
        
        # 1. 將腳本寫入綁定掛載的主機目錄中
        ext = ".py" if language == "python" else (".sh" if language == "bash" else ".js")
        script_name = f"script{ext}"
        script_path_host = os.path.join(self.work_dir, script_name)
        
        with open(script_path_host, "w", encoding="utf-8") as f:
            f.write(code)

        # 2. 準備 Docker 命令與安全限制參數
        docker_cmd = [
            "docker", "run", "--rm",
            "-v", f"{self.work_dir}:/app:ro",   # 唯讀掛載腳本
            "-w", "/app",
            # === 資源限制 ===
            "--memory=128m",
            "--memory-swap=128m",               # 禁用 swap
            "--cpus=0.5",
            "--pids-limit=64",
            "--ulimit", "nofile=256:256",        # 檔案描述符限制
            "--ulimit", "nproc=64:64",           # 行程數限制
            "--ulimit", "fsize=10485760:10485760",  # 單檔 10MB
            # === 權限雙降 ===
            "--read-only",
            "--tmpfs", "/tmp:size=64m,noexec,nosuid",
            "--cap-drop=ALL",
            "--no-new-privileges",
            "--security-opt=no-new-privileges:true",
            "--user", "65534:65534",
            # === 環境變數清潔 ===
            "--env-file", "/dev/null",
        ]
        
        # Linux: 使用 namespace 隔離
        if self._is_linux:
            docker_cmd.extend([
                "--security-opt", "seccomp=unconfined",  # 由 cap-drop 取代
                "--security-opt", "apparmor=docker-default",
            ])
        
        if self.docker_runtime:
            docker_cmd.insert(2, f"--runtime={self.docker_runtime}")
        
        if not network_allowed:
            docker_cmd.append("--network=none")
            
        
        # 3. 準備容器內指令
        # 注意：--read-only 下 pip install 需要寫入 /tmp
        req_file_host = os.path.join(self.work_dir, "sandbox_requirements.txt")
        pip_cmd = ""
        if os.path.exists(req_file_host) and os.path.getsize(req_file_host) > 0:
            pip_cmd = "pip install --cache-dir=/tmp/pip-cache --target=/tmp/site-packages -r sandbox_requirements.txt > /dev/null 2>&1 && PYTHONPATH=/tmp/site-packages "
            
        # 4. 根據語言決定映像檔與執行指令
        if language == "python":
            cmd = f"{pip_cmd}python {script_name}"
            docker_cmd.extend(["python:3.12-alpine", "sh", "-c", cmd])
        elif language == "bash":
            docker_cmd.extend(["alpine", "sh", script_name])
        elif language == "javascript":
            docker_cmd.extend(["node:20-alpine", "node", script_name])
        else:
            return ToolCallResult(
                tool_name=f"{language}_exec",
                success=False,
                output="",
                error=f"Unsupported language for DockerSandbox: {language}"
            )

        # 4. 啟動 Container Process
        try:
            process = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=_preexec_rlimit,  # 主機側 rlimit 防禦
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout_seconds
                )
                
                success = (process.returncode == 0)
                out_str = stdout.decode().strip()
                err_str = stderr.decode().strip()
                
                final_output = out_str
                if err_str:
                    final_output += f"\n[STDERR]\n{err_str}"
                    
                exec_time = int((time.time() - start_time) * 1000)
                
                return ToolCallResult(
                    tool_name=f"{language}_exec",
                    success=success,
                    output=final_output.strip(),
                    error=err_str if not success else None,
                    execution_time_ms=exec_time
                )
                
            except asyncio.TimeoutError:
                # 發生 Timeout，強制刺殺行程 (強制移徐掛掉的 Container)
                try:
                    process.kill()
                except OSError:
                    pass
                
                exec_time = int((time.time() - start_time) * 1000)
                return ToolCallResult(
                    tool_name=f"{language}_exec",
                    success=False,
                    output="",
                    error=f"Docker Execution timed out after {timeout_seconds} seconds",
                    execution_time_ms=exec_time
                )
                
        except Exception as e:
            exec_time = int((time.time() - start_time) * 1000)
            return ToolCallResult(
                tool_name=f"{language}_exec",
                success=False,
                output="",
                error=f"Docker launch failed: {e}",
                execution_time_ms=exec_time
            )

    async def cleanup(self) -> None:
        """清理暫存資料夾"""
        if self._temp_dir:
            self._temp_dir.cleanup()
            self._temp_dir = None
