"""
03_Tool_System — 沙盒管理器 (Sandbox Manager)
=============================================
負責管理和調度沙盒執行環境。
與 MemoryManager 類似，SandboxManager 隱藏了底層 SandboxProvider 的細節。
Engine 呼叫 SandboxManager 時，不需關心底層是 Subprocess, Pyodide 還是 E2B。
"""

import logging
from typing import Optional

from config_schema import AgentOSConfig
from contracts.interfaces import SandboxProvider, ToolCallResult

logger = logging.getLogger(__name__)


class SandboxManager:
    """
    沙盒統一管理器
    """

    def __init__(self, config: AgentOSConfig, provider: SandboxProvider):
        self.config = config
        self._provider = provider
        logger.info(f"🛡️ Sandbox Manager 初始化完成，使用提供者: {type(provider).__name__}")

    @property
    def provider(self) -> SandboxProvider:
        return self._provider

    def set_provider(self, provider: SandboxProvider) -> None:
        """熱切換沙盒環境"""
        logger.info(f"🔄 Sandbox Provider 切換為: {type(provider).__name__}")
        self._provider = provider

    async def execute(
        self,
        code: str,
        language: str = "python",
        timeout_seconds: Optional[int] = None,
        network_allowed: Optional[bool] = None,
    ) -> ToolCallResult:
        """
        在沙盒中執行代碼。
        若未提供 timeout 參數，則使用 config.yaml 中的預設值。
        """
        # 套用 config 預設設定
        sandbox_cfg = self.config.sandbox
        
        final_timeout = timeout_seconds if timeout_seconds is not None else sandbox_cfg.timeout_seconds
        
        if network_allowed is None:
            final_network = (sandbox_cfg.default_network == "allow")
        else:
            final_network = network_allowed

        logger.debug(f"▶️ 準備執行沙盒代碼 (語言: {language}, 超時: {final_timeout}s, 網路允許: {final_network})")
        
        try:
            # 委派給底層 Provider 執行
            result = await self._provider.execute(
                code=code,
                language=language,
                timeout_seconds= final_timeout,
                network_allowed=final_network,
            )
            return result
            
        except Exception as e:
            logger.error(f"❌ 沙盒執行發生嚴重的系統層外掛錯誤: {e}")
            return ToolCallResult(
                tool_name="sandbox_execute",
                success=False,
                output="",
                error=f"Sandbox system error: {str(e)}"
            )

    async def cleanup(self) -> None:
        """
        清理沙盒環境，釋放資源。
        """
        try:
            await self._provider.cleanup()
            logger.info("🧹 Sandbox 環境已清理")
        except Exception as e:
            logger.error(f"⚠️ Sandbox 清理失敗: {e}")
