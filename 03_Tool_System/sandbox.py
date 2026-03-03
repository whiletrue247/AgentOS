"""
03_Tool_System — 沙盒管理器 (Sandbox Manager)
=============================================
負責管理和調度沙盒執行環境。
與 MemoryManager 類似，SandboxManager 隱藏了底層 SandboxProvider 的細節。
Engine 呼叫 SandboxManager 時，不需關心底層是 Subprocess, Pyodide 還是 E2B。
"""

import logging
import re
from typing import Optional

from config_schema import AgentOSConfig
from contracts.interfaces import SandboxProvider, ToolCallResult

logger = logging.getLogger(__name__)

# 危險代碼模式（主機逃逸向量）
_DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    # 環境變數竊取
    (r"os\.environ", "存取主機環境變數 (os.environ)"),
    (r"os\.getenv", "存取主機環境變數 (os.getenv)"),
    # 子行程程逃逸
    (r"subprocess\.(?:run|call|Popen|check_output)", "試圖透過 subprocess 執行主機指令"),
    (r"os\.(?:system|popen|exec[lv]p?e?)", "試圖透過 os 執行主機指令"),
    # 網路逃逸
    (r"socket\.socket", "試圖建立原始 socket 連線"),
    # 低階攻擊
    (r"ctypes\.(?:cdll|CDLL|windll)", "試圖透過 ctypes 載入原生函式庫"),
    (r"exec_module\s*\(", "動態載入並執行模組 (RCE 向量)"),
    # 檔案系統攻擊
    (r"/proc/", "存取 /proc 檔案系統"),
    (r"/etc/(?:shadow|passwd|sudoers)", "存取系統敦感檔案"),
    (r"shutil\.rmtree\s*\(\s*['\"/]", "尚試刪除根目錄"),
    # fork bomb
    (r"os\.fork\s*\(", "試圖 fork bomb"),
]
_DANGEROUS_REGEXES = [(re.compile(p, re.IGNORECASE), desc) for p, desc in _DANGEROUS_PATTERNS]

# 代碼長度上限 (bytes)
_MAX_CODE_LENGTH = 100_000  # 100 KB


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
        執行前會進行安全掃描（代碼長度 + 危險模式）。
        若未提供 timeout 參數，則使用 config.yaml 中的預設值。
        """
        # ── 安全掃描層 (縱深防禦) ──
        safety_result = self._scan_code_safety(code, language)
        if safety_result is not None:
            return safety_result

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
                timeout_seconds=final_timeout,
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

    @staticmethod
    def _scan_code_safety(code: str, language: str) -> Optional[ToolCallResult]:
        """
        執行前安全掃描（縱深防禦層，在 Docker 之上額外保護）。
        回傳 None 表示通過，回傳 ToolCallResult 表示被攔截。
        """
        # 1. 代碼長度檢查
        code_bytes = len(code.encode('utf-8'))
        if code_bytes > _MAX_CODE_LENGTH:
            logger.warning(f"🚨 [Sandbox] 代碼超過長度上限 ({code_bytes}/{_MAX_CODE_LENGTH} bytes)")
            return ToolCallResult(
                tool_name="sandbox_execute",
                success=False,
                output="",
                error=f"Code exceeds maximum length ({_MAX_CODE_LENGTH} bytes)"
            )

        # 2. 危險模式掃描 (僅對 Python 和 bash 執行)
        if language in ("python", "bash"):
            for regex, description in _DANGEROUS_REGEXES:
                match = regex.search(code)
                if match:
                    logger.warning(
                        f"🚨 [Sandbox] 危險代碼被攔截: {description} "
                        f"(匹配: '{match.group()}')"
                    )
                    return ToolCallResult(
                        tool_name="sandbox_execute",
                        success=False,
                        output="",
                        error=f"Security scan blocked: {description}"
                    )

        return None  # 通過掃描

    async def cleanup(self) -> None:
        """
        清理沙盒環境，釋放資源。
        """
        try:
            await self._provider.cleanup()
            logger.info("🧹 Sandbox 環境已清理")
        except Exception as e:
            logger.error(f"⚠️ Sandbox 清理失敗: {e}")
