"""
Docker 沙盒 (DockerSandbox)
========================================
基於 Docker CLI 實作的主機實體隔離沙盒。
這提供強大的安全邊界，防止 Agent 執行如 `rm -rf /` 或 fork bomb 等惡意操作。
"""

import asyncio
import logging
import os
import tempfile
import time
from typing import Optional

from contracts.interfaces import SandboxProvider, ToolCallResult

logger = logging.getLogger(__name__)


class DockerSandbox(SandboxProvider):
    """
    基於 Docker Container 的安全沙盒
    """

    def __init__(self, work_dir: Optional[str] = None, docker_runtime: str = ""):
        self.docker_runtime = docker_runtime
        if work_dir:
            self.work_dir = work_dir
            self._temp_dir = None
        else:
            # 在主機建立掛載用的暫存目錄
            self._temp_dir = tempfile.TemporaryDirectory(prefix="agentos_docker_")
            self.work_dir = self._temp_dir.name
            
        logger.info(f"🐳 DockerSandbox 初始化完成，掛載目錄: {self.work_dir}")

    async def execute(
        self,
        code: str,
        language: str = "python",
        timeout_seconds: int = 60,
        network_allowed: bool = False,
        agent_role: str = "default",
    ) -> ToolCallResult:
        """
        在受限的 Docker 容器中執行腳本。(含 Zero Trust 攔截)
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
        # - --rm : 執行完畢自動刪除容器
        # - -v : 掛載腳本目錄到容器內的 /app
        # - -w /app : 設定工作目錄
        # - --memory : 防止記憶體炸彈 (128MB)
        # - --cpus : 防止 CPU 吃滿
        # - --network none : 如果不允許網路，則完全斷網
        
        docker_cmd = [
            "docker", "run", "--rm",
            "-v", f"{self.work_dir}:/app",
            "-w", "/app",
            "--memory=128m",
            "--cpus=0.5",
        ]
        
        if self.docker_runtime:
            docker_cmd.insert(2, f"--runtime={self.docker_runtime}")
        
        if not network_allowed:
            docker_cmd.append("--network=none")
            
        
        # 3. 準備容器內指令
        # 如果有 sandbox_requirements.txt，就先安裝再執行
        req_file_host = os.path.join(self.work_dir, "sandbox_requirements.txt")
        pip_cmd = ""
        if os.path.exists(req_file_host) and os.path.getsize(req_file_host) > 0:
            pip_cmd = "pip install -r sandbox_requirements.txt > /dev/null 2>&1 && "
            
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
