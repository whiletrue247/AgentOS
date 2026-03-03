"""
03_Tool_System — E2B Cloud Sandbox Provider
=============================================
基於 E2B (e2b.dev) 的雲端 MicroVM 沙盒。
提供 VM 級別隔離，每次執行創建全新的沙盒環境。

依賴：
  pip install e2b-code-interpreter

配置：
  config.yaml:
    sandbox:
      runtime: e2b        # 切換到 E2B
      e2b_api_key: ...    # E2B API Key

TODO: 完整實作等待 E2B API Key 配置後啟用。
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from e2b_code_interpreter import Sandbox as E2BSandbox
    E2B_AVAILABLE = True
except ImportError:
    E2B_AVAILABLE = False

try:
    from contracts.interfaces import SandboxProvider, ToolCallResult
except ImportError:
    from interfaces import SandboxProvider, ToolCallResult


class E2BCloudSandbox:
    """
    E2B 雲端 MicroVM 沙盒 Provider。
    
    每次 execute() 建立新的沙盒環境 (5 秒冷啟動)，
    提供完整 VM 級別隔離，無需本地 Docker。
    
    Args:
        api_key: E2B API Key
        template: 沙盒模板 (預設 Python)
        timeout_seconds: 預設超時
    """

    def __init__(
        self,
        api_key: str = "",
        template: str = "Python3",
        timeout_seconds: int = 60,
    ):
        if not E2B_AVAILABLE:
            raise ImportError(
                "e2b-code-interpreter is required: pip install e2b-code-interpreter"
            )
        if not api_key:
            raise ValueError("E2B API Key is required (config.yaml: sandbox.e2b_api_key)")

        self._api_key = api_key
        self._template = template
        self._default_timeout = timeout_seconds
        self._sandbox: Optional[E2BSandbox] = None

        logger.info(
            f"☁️ E2BCloudSandbox 初始化: template={template}, "
            f"timeout={timeout_seconds}s"
        )

    async def execute(
        self,
        code: str,
        language: str = "python",
        timeout_seconds: int = 60,
        network_allowed: bool = False,
    ) -> ToolCallResult:
        """
        在 E2B 雲端 MicroVM 中執行代碼。
        
        Args:
            code: 要執行的代碼
            language: 程式語言 (目前僅支援 python)
            timeout_seconds: 超時秒數
            network_allowed: 是否允許網路 (E2B 預設隔離)
            
        Returns:
            ToolCallResult 執行結果
        """
        if language != "python":
            return ToolCallResult(
                tool_name="sandbox_execute",
                success=False,
                output="",
                error=f"E2B sandbox currently only supports Python, got: {language}",
            )

        try:
            # 建立新沙盒
            sandbox = E2BSandbox(api_key=self._api_key, template=self._template)

            # 執行代碼
            execution = sandbox.run_code(code, timeout=timeout_seconds)

            # 收集輸出
            stdout = "".join(
                r.text for r in execution.logs.stdout
            ) if execution.logs.stdout else ""
            stderr = "".join(
                r.text for r in execution.logs.stderr
            ) if execution.logs.stderr else ""

            output = stdout
            if stderr:
                output += f"\n[stderr]: {stderr}"

            error = execution.error.message if execution.error else None

            # 關閉沙盒
            sandbox.kill()

            return ToolCallResult(
                tool_name="sandbox_execute",
                success=error is None,
                output=output[:10000],  # 截斷
                error=error,
                truncated=len(output) > 10000,
            )

        except Exception as e:
            logger.error(f"❌ E2B sandbox error: {e}")
            return ToolCallResult(
                tool_name="sandbox_execute",
                success=False,
                output="",
                error=f"E2B sandbox error: {str(e)}",
            )

    async def cleanup(self) -> None:
        """清理沙盒環境"""
        if self._sandbox:
            try:
                self._sandbox.kill()
            except Exception:
                pass
            self._sandbox = None
        logger.info("🧹 E2B Sandbox 環境已清理")
