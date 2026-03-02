"""
04_Engine — Cost Guard (預算守衛)
================================
追蹤 Token 消耗量（單位：M = 百萬 Token）。
功能：
  1. 記錄每次 API 呼叫的 input/output tokens
  2. 計算每日 M 消耗
  3. 執行前預估任務成本 (warn_before_task)
  4. 超過 daily_limit_m 時阻止呼叫
  5. 產生 CostReport 給 Dashboard 顯示
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from config_schema import AgentOSConfig
from contracts.interfaces import APICallRecord, CostReport

logger = logging.getLogger(__name__)

M = 1_000_000  # 1M = 100 萬 token


class CostGuard:
    """
    Token 消耗追蹤 + 預算守衛。
    """

    def __init__(self, config: AgentOSConfig, history_path: str = "./logs/cost_history.json"):
        self.config = config
        self._history_path = Path(history_path)
        self._records: list[APICallRecord] = []

        # 每日統計快取 { "2026-03-03": { "input": 12345, "output": 6789 } }
        self._daily: dict[str, dict[str, int]] = defaultdict(lambda: {"input": 0, "output": 0})

        # 載入歷史
        self._load_history()

    # ========================================
    # 記錄
    # ========================================

    def record(self, call: APICallRecord) -> None:
        """記錄一筆 API 呼叫"""
        self._records.append(call)
        day_key = call.timestamp.strftime("%Y-%m-%d")
        self._daily[day_key]["input"] += call.input_tokens
        self._daily[day_key]["output"] += call.output_tokens

        total = call.input_tokens + call.output_tokens
        logger.debug(f"💰 記錄: {call.model} in:{call.input_tokens} out:{call.output_tokens} (+{total/M:.4f}M)")

        # 定期存檔
        if len(self._records) % 10 == 0:
            self._save_history()

    def record_from_gateway(self, gateway) -> None:
        """從 APIGateway 的 call_history 批次匯入"""
        for call in gateway.get_call_history():
            if call not in self._records:
                self.record(call)

    # ========================================
    # 查詢
    # ========================================

    @property
    def today_key(self) -> str:
        return date.today().strftime("%Y-%m-%d")

    @property
    def today_input_tokens(self) -> int:
        return self._daily[self.today_key]["input"]

    @property
    def today_output_tokens(self) -> int:
        return self._daily[self.today_key]["output"]

    @property
    def today_total_tokens(self) -> int:
        return self.today_input_tokens + self.today_output_tokens

    @property
    def today_m(self) -> float:
        """今日消耗多少 M"""
        return self.today_total_tokens / M

    @property
    def daily_limit_m(self) -> float:
        return self.config.budget.daily_limit_m

    @property
    def budget_remaining_m(self) -> float:
        return max(0.0, self.daily_limit_m - self.today_m)

    @property
    def budget_remaining_pct(self) -> float:
        if self.daily_limit_m <= 0:
            return 0.0
        return (self.budget_remaining_m / self.daily_limit_m) * 100

    # ========================================
    # 預算守衛
    # ========================================

    def check_budget(self) -> tuple[bool, str]:
        """
        檢查是否還有預算。
        回傳: (can_proceed, message)
        """
        if self.today_m >= self.daily_limit_m:
            msg = f"🚫 每日預算已用盡: {self.today_m:.3f}M / {self.daily_limit_m:.1f}M"
            logger.warning(msg)
            return False, msg

        if self.budget_remaining_pct < 10:
            msg = f"⚠️ 預算即將用盡: 剩餘 {self.budget_remaining_m:.3f}M ({self.budget_remaining_pct:.1f}%)"
            logger.warning(msg)
            return True, msg

        return True, ""

    def estimate_task_cost(self, estimated_input: int, estimated_output: int) -> str:
        """
        預估一個任務的成本。在任務開始前呼叫。
        """
        est_total = estimated_input + estimated_output
        est_m = est_total / M
        remaining = self.budget_remaining_m

        if est_m > remaining:
            return (
                f"⚠️ 預估耗費 {est_m:.4f}M，但今日剩餘 {remaining:.3f}M。"
                f" 建議精簡任務或提高 daily_limit_m。"
            )
        return f"📊 預估耗費 {est_m:.4f}M（當前剩餘 {remaining:.3f}M）"

    # ========================================
    # 報告
    # ========================================

    def get_report(self) -> CostReport:
        """產生 CostReport 供 Dashboard 使用"""
        total_in = sum(r.input_tokens for r in self._records)
        total_out = sum(r.output_tokens for r in self._records)
        total = total_in + total_out

        # 歷史每日統計
        history = []
        for day_key in sorted(self._daily.keys()):
            d = self._daily[day_key]
            history.append({
                "date": day_key,
                "input_m": d["input"] / M,
                "output_m": d["output"] / M,
            })

        today_calls = sum(
            1 for r in self._records
            if r.timestamp.strftime("%Y-%m-%d") == self.today_key
        )

        return CostReport(
            total_input_tokens=total_in,
            total_output_tokens=total_out,
            total_tokens=total,
            total_m=total / M,
            daily_m=self.today_m,
            daily_limit_m=self.daily_limit_m,
            budget_remaining_pct=self.budget_remaining_pct,
            calls_today=today_calls,
            history=history,
        )

    # ========================================
    # 持久化
    # ========================================

    def _save_history(self) -> None:
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "daily": dict(self._daily),
            "total_records": len(self._records),
        }
        with open(self._history_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_history(self) -> None:
        if not self._history_path.exists():
            return
        try:
            with open(self._history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for day_key, stats in data.get("daily", {}).items():
                self._daily[day_key] = stats
            logger.info(f"📊 Cost history 已載入: {len(self._daily)} 天紀錄")
        except Exception as e:
            logger.warning(f"⚠️ 載入 cost history 失敗: {e}")

    def save(self) -> None:
        """手動存檔"""
        self._save_history()
