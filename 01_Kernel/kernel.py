"""
01_Kernel — 靈魂載入器
======================
負責在 OS 啟動時載入 SOUL.md，作為 Agent 的核心 System Prompt。
依據 OS 中立原則，此模組「不解析」SOUL.md 的內部結構，僅作為純文字載入。
"""

import logging
from pathlib import Path
from typing import Optional

# 由於是在同一層級或上層，需確認 import 方式
# 這裡預設會從 Agent_Base_OS 根目錄執行，因此可直接 import contracts
from contracts.interfaces import KernelConfig

logger = logging.getLogger(__name__)


class Kernel:
    def __init__(self, config: Optional[KernelConfig] = None):
        self.config = config or KernelConfig()
        
    def load_soul(self) -> str:
        """
        從路徑讀取 SOUL.md
        """
        soul_path = Path(self.config.soul_path)
        
        if not soul_path.exists():
            default_prompt = "You are a helpful AI Agent. (SOUL.md not found)"
            logger.warning(f"⚠️ 找不到 SOUL.md (預期路徑: {soul_path.absolute()})。使用預設 Prompt。")
            self.config.soul_content = default_prompt
            return default_prompt
            
        try:
            with open(soul_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    logger.warning(f"⚠️ SOUL.md 為空。")
                    content = "You are a helpful AI Agent."
                self.config.soul_content = content
                return content
        except Exception as e:
            logger.error(f"❌ 讀取 SOUL.md 失敗: {e}")
            self.config.soul_content = "You are a helpful AI Agent."
            return self.config.soul_content

    def get_system_prompt(self) -> str:
        """
        取得最終要注入到大模型 System Prompt 的文本。
        """
        if not self.config.soul_content:
            self.load_soul()
        return self.config.soul_content
