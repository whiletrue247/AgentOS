"""
04_Engine — Evolution Scheduler (每日自動進化)
================================================
定期執行 SoulEvolver.run_cycle()，自動完成：
  Memory 掃描 → SOUL 畢業 → LoRA 微調

復用 DecayScheduler 的 asyncio background task 模式。
預設每 24 小時執行一次。

用法：
  scheduler = EvolutionScheduler(evolver)
  await scheduler.start()
  # ... (背景自動運行)
  await scheduler.stop()
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class EvolutionScheduler:
    """
    定時觸發 SoulEvolver.run_cycle() 的背景排程器。
    
    Args:
        evolver: SoulEvolver 實例
        interval_seconds: 執行間隔 (預設 86400 = 24h)
        run_on_start: 啟動時立即執行一次
    """

    def __init__(
        self,
        evolver: Any,
        interval_seconds: float = 86400,
        run_on_start: bool = False,
    ):
        self._evolver = evolver
        self._interval = interval_seconds
        self._run_on_start = run_on_start
        self._running = False
        self._task: asyncio.Task | None = None
        self._total_graduated = 0

    async def start(self) -> None:
        """啟動背景進化排程"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            f"🧬 EvolutionScheduler started: "
            f"interval={self._interval}s, "
            f"run_on_start={self._run_on_start}"
        )

    async def stop(self) -> None:
        """停止排程"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(
            f"🧬 EvolutionScheduler stopped. "
            f"Total graduated: {self._total_graduated}"
        )

    async def _loop(self) -> None:
        """背景迴圈"""
        if self._run_on_start:
            await self._run_once()

        while self._running:
            try:
                await asyncio.sleep(self._interval)
                await self._run_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ EvolutionScheduler error: {e}")
                # 不中斷排程，等下次再試
                await asyncio.sleep(60)

    async def _run_once(self) -> int:
        """執行一次進化週期"""
        logger.info("🔄 EvolutionScheduler: 觸發每日進化...")
        try:
            count = await self._evolver.run_cycle()
            self._total_graduated += count
            logger.info(
                f"✅ 每日進化完成: 本次畢業 {count} 條, "
                f"累計 {self._total_graduated} 條"
            )
            return count
        except Exception as e:
            logger.error(f"❌ 進化週期失敗: {e}")
            return 0

    @property
    def stats(self) -> dict:
        """取得排程器統計"""
        return {
            "running": self._running,
            "interval_seconds": self._interval,
            "total_graduated": self._total_graduated,
        }
