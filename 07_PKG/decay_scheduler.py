"""
07_PKG — Knowledge Decay Scheduler
====================================
定期執行圖譜權重衰減，讓 7 天未被存取的實體關係自動消退。
可被 cron、APScheduler、或 Engine 事件迴圈驅動。
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class DecayScheduler:
    """
    定時執行 PersonalKnowledgeGraph.apply_decay()。
    預設每 24 小時執行一次，half_life 為 7 天。
    """

    def __init__(
        self,
        kg: Any,
        interval_seconds: float = 86400,   # 預設每 24 小時
        half_life_days: float = 7.0,
        min_weight: float = 0.05,
    ):
        self.kg = kg
        self.interval = interval_seconds
        self.half_life = half_life_days
        self.min_weight = min_weight
        self._running = False
        self._task = None

    async def start(self):
        """啟動背景衰減排程"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            f"⏰ Decay scheduler started: interval={self.interval}s, "
            f"half_life={self.half_life}d, min_weight={self.min_weight}"
        )

    async def stop(self):
        """停止排程"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("⏰ Decay scheduler stopped")

    async def _loop(self):
        while self._running:
            try:
                await asyncio.sleep(self.interval)
                self.run_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Decay scheduler error: {e}")

    def run_once(self) -> int:
        """手動觸發一次衰減 (供測試或 CLI 使用)"""
        logger.info("🧹 Running knowledge decay...")
        deleted = self.kg.apply_decay(
            half_life_days=self.half_life,
            min_weight=self.min_weight,
        )
        stats = self.kg.display_stats()
        logger.info(
            f"✅ Decay complete: {deleted} edges removed. "
            f"Remaining: {stats.get('nodes', 0)} nodes, {stats.get('edges', 0)} edges"
        )
        return deleted
