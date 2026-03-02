"""
本地 Subprocess 沙盒 (SubprocessSandbox)
========================================
作為 Pyodide/E2B 不可用時的 fallback。
這不是真正的虛擬機器，只能提供基本的執行功能與粗糙的隔離。
限制手段：
- 執行緒 Timeout
- macOS 上無法像 Linux namespace 那樣輕易斷網，因此透過設定非法的 HTTP_PROXY 達到簡單的網路斷網（Best Effort）。
"""

import asyncio
import logging
import os
import sys
import tempfile
import time
from typing import Optional

from contracts.interfaces import SandboxProvider, ToolCallResult

logger = logging.getLogger(__name__)


class SubprocessSandbox:
    """
    基於 asyncio.create_subprocess_exec 的本地沙盒
    """

    def __init__(self, work_dir: Optional[str] = None):
        if work_dir:
            self.work_dir = work_dir
            self._temp_dir = None
        else:
            self._temp_dir = tempfile.TemporaryDirectory(prefix="agentos_sandbox_")
            self.work_dir = self._temp_dir.name
            
        logger.info(f"📁 Subprocess 工作目錄: {self.work_dir}")

    async def execute(
        self,
        code: str,
        language: str = "python",
        timeout_seconds: int = 60,
        network_allowed: bool = False,
    ) -> ToolCallResult:
        """
        執行腳本。
        """
        start_time = time.time()
        
        # 1. 寫入腳本檔案
        ext = ".py" if language == "python" else (".sh" if language == "bash" else ".js")
        script_path = os.path.join(self.work_dir, f"script{ext}")
        
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code)

        # 2. 準備環境變數 (模擬斷網)
        env = os.environ.copy()
        if not network_allowed:
            # Best effort 斷網：設定非法的 Proxy
            env["http_proxy"] = "http://127.0.0.1:1"
            env["https_proxy"] = "http://127.0.0.1:1"
            env["NO_PROXY"] = "localhost,127.0.0.1"

        # 3. 決定執行指令
        if language == "python":
            cmd = [sys.executable, script_path]
        elif language == "bash":
            cmd = ["bash", script_path]
        elif language == "javascript":
            cmd = ["node", script_path]
        else:
            return ToolCallResult(
                tool_name=f"{language}_exec",
                success=False,
                output="",
                error=f"Unsupported language: {language}"
            )

        # 4. 啟動 Process
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.work_dir,
                env=env,
            )
            
            # 使用 asyncio.wait_for 加入 Timeout 控制
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout_seconds
                )
                
                success = (process.returncode == 0)
                out_str = stdout.decode().strip()
                err_str = stderr.decode().strip()
                
                # 合併 stdout 和 stderr
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
                # 發生 Timeout，強制刺殺行程
                try:
                    process.kill()
                except OSError:
                    pass
                
                exec_time = int((time.time() - start_time) * 1000)
                return ToolCallResult(
                    tool_name=f"{language}_exec",
                    success=False,
                    output="",
                    error=f"Execution timed out after {timeout_seconds} seconds",
                    execution_time_ms=exec_time
                )
                
        except Exception as e:
            exec_time = int((time.time() - start_time) * 1000)
            return ToolCallResult(
                tool_name=f"{language}_exec",
                success=False,
                output="",
                error=f"Process launch failed: {e}",
                execution_time_ms=exec_time
            )

    async def cleanup(self) -> None:
        """清理暫存資料夾"""
        if self._temp_dir:
            self._temp_dir.cleanup()
            self._temp_dir = None
