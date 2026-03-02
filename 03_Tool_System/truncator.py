"""
03_Tool_System — 輸出截斷器 (Truncator)
=======================================
負責處理工具執行後，輸出字串過長的問題，避免 Token 爆炸。
根據 config.yaml 中的 `sandbox.truncation` 設定：
- threshold: 觸發截斷的長度閾值
- head_ratio: 保留頭部的比例 (例如 0.1 代表保留前 10% 的內容)
- tail_ratio: 保留尾部的比例
- disabled: 是否完全停用截斷

特點：中段會被替換為 `\n... [Truncated {X} characters] ...\n`
"""

import logging
from typing import Optional

from config_schema import AgentOSConfig
from contracts.interfaces import ToolCallResult

logger = logging.getLogger(__name__)


class Truncator:
    """工具輸出截斷器"""

    def __init__(self, config: Optional[AgentOSConfig] = None):
        self.config = config or AgentOSConfig()

    def truncate_text(self, text: str) -> tuple[str, bool]:
        """
        截斷原始文本。
        回傳: (處理後的文本, 是否發生了截斷)
        """
        if not text:
            return text, False

        t_config = self.config.sandbox.truncation

        if t_config.disabled:
            return text, False

        length = len(text)
        if length <= t_config.threshold:
            return text, False

        # 計算分配長度
        head_len = int(t_config.threshold * t_config.head_ratio)
        tail_len = int(t_config.threshold * t_config.tail_ratio)

        # 邊界防護，避免 ratio 設定錯誤導致全空
        if head_len + tail_len <= 0:
            logger.warning("⚠️ head_ratio 和 tail_ratio 為 0，強制只保留 200 字 tail")
            tail_len = min(200, t_config.threshold)
        
        # 確保總長不超過 threshold
        if head_len + tail_len > t_config.threshold:
            # 等比例縮小
            scale = t_config.threshold / (head_len + tail_len)
            head_len = int(head_len * scale)
            tail_len = int(tail_len * scale)

        head_part = text[:head_len] if head_len > 0 else ""
        tail_part = text[-tail_len:] if tail_len > 0 else ""
        
        omitted = length - head_len - tail_len
        
        mid_marker = f"\n\n... [Truncated {omitted} characters. Full output not shown.] ...\n\n"
        
        result = head_part + mid_marker + tail_part
        return result, True

    def process_result(self, result: ToolCallResult) -> ToolCallResult:
        """
        對 ToolCallResult 進行 in-place 截斷處理並回傳。
        """
        if result.success and result.output:
            truncated_out, was_truncated = self.truncate_text(result.output)
            result.output = truncated_out
            result.truncated = was_truncated
            if was_truncated:
                logger.debug(f"✂️ {result.tool_name} 輸出已截斷 (原始長度: {len(result.output)})")
                
        # error 欄位通常不會非常誇張，但也略作保護 (強制 5000 字元上限)
        if not result.success and result.error and len(result.error) > 5000:
            result.error = result.error[:2500] + "\n... [Error Truncated] ...\n" + result.error[-2500:]
            result.truncated = True
                
        return result
