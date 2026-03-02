"""
04_Engine — Rate Limiter (Token Bucket)
=======================================
RPM (Requests Per Minute) 和 TPM (Tokens Per Minute) 的雙重速率限制。
使用經典的 Token Bucket 演算法。

用法：
    limiter = RateLimiter(rpm=30, tpm=100_000)
    await limiter.acquire(estimated_tokens=500)  # 若超限則自動等待
"""

from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class TokenBucket:
    """
    單一 Token Bucket。
    以固定速率補充 token，消耗時扣減。
    """

    def __init__(self, capacity: int, refill_rate: float):
        """
        capacity: 桶容量
        refill_rate: 每秒補充幾個 token
        """
        self.capacity = capacity
        self.tokens = float(capacity)
        self.refill_rate = refill_rate
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self._last_refill = now

    def try_consume(self, amount: int = 1) -> bool:
        """嘗試消耗 token，成功回傳 True"""
        self._refill()
        if self.tokens >= amount:
            self.tokens -= amount
            return True
        return False

    def wait_time(self, amount: int = 1) -> float:
        """計算需要等多久才能拿到 amount 個 token"""
        self._refill()
        if self.tokens >= amount:
            return 0.0
        deficit = amount - self.tokens
        return deficit / self.refill_rate


class RateLimiter:
    """
    雙重速率限制器：同時控制 RPM 和 TPM。
    """

    def __init__(self, rpm: int = 30, tpm: int = 100_000):
        # RPM bucket: capacity = rpm, refill = rpm/60 per second
        self._rpm_bucket = TokenBucket(capacity=rpm, refill_rate=rpm / 60.0)
        # TPM bucket: capacity = tpm, refill = tpm/60 per second
        self._tpm_bucket = TokenBucket(capacity=tpm, refill_rate=tpm / 60.0)
        self._rpm = rpm
        self._tpm = tpm

        logger.info(f"⏱️ Rate Limiter 啟動: RPM={rpm}, TPM={tpm}")

    async def acquire(self, estimated_tokens: int = 1) -> None:
        """
        嘗試取得發送許可。如果超限，自動 await 等到有配額。
        """
        # 先等 RPM
        wait_rpm = self._rpm_bucket.wait_time(1)
        wait_tpm = self._tpm_bucket.wait_time(estimated_tokens)
        wait = max(wait_rpm, wait_tpm)

        if wait > 0:
            logger.warning(f"⏳ Rate limit 觸發，等待 {wait:.2f}s (RPM wait: {wait_rpm:.2f}s, TPM wait: {wait_tpm:.2f}s)")
            await asyncio.sleep(wait)

        # 消耗 token
        self._rpm_bucket.try_consume(1)
        self._tpm_bucket.try_consume(estimated_tokens)

    @property
    def rpm_remaining(self) -> float:
        self._rpm_bucket._refill()
        return self._rpm_bucket.tokens

    @property
    def tpm_remaining(self) -> float:
        self._tpm_bucket._refill()
        return self._tpm_bucket.tokens
