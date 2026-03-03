"""
10_Marketplace — Rating System (Sprint 4)
==========================================
工具和 SOUL 模板的評分與品質保證系統。

功能：
  - 1-5 星評分 + 文字評論
  - 滾動移動平均計算
  - 安全掃描標籤 (自動/手動)
  - 評論持久化 (JSON 儲存)
  - 品質排行榜
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from paths import get_data_dir

__all__ = ["RatingSystem", "Review", "QualityReport"]

logger = logging.getLogger(__name__)

_REVIEWS_FILE = get_data_dir() / "marketplace_reviews.json"


@dataclass
class Review:
    """單筆評論"""
    reviewer: str         # 評論者 ID
    tool_id: str
    score: float          # 1.0 ~ 5.0
    comment: str = ""
    timestamp: str = ""
    security_labels: List[str] = field(default_factory=list)  # e.g. ["ast_safe", "hash_verified"]


@dataclass
class QualityReport:
    """工具品質報告"""
    tool_id: str
    avg_score: float = 0.0
    total_reviews: int = 0
    security_labels: List[str] = field(default_factory=list)
    recent_reviews: List[Review] = field(default_factory=list)
    rank: int = 0  # 全局排名


class RatingSystem:
    """
    Marketplace 評分與品質保證系統。

    使用方式：
        rs = RatingSystem()
        rs.submit_review("tool_x", score=4.5, comment="Great!", reviewer="user_a")
        report = rs.get_quality_report("tool_x")
    """

    def __init__(self):
        self._reviews: Dict[str, List[Review]] = {}
        self._security_labels: Dict[str, List[str]] = {}
        self._load()

    def submit_review(
        self,
        tool_id: str,
        score: float,
        comment: str = "",
        reviewer: str = "anonymous",
    ) -> bool:
        """提交評論"""
        if not (1.0 <= score <= 5.0):
            logger.error(f"❌ 評分必須在 1.0~5.0 之間，收到 {score}")
            return False

        review = Review(
            reviewer=reviewer,
            tool_id=tool_id,
            score=score,
            comment=comment,
            timestamp=datetime.now().isoformat(),
            security_labels=list(self._security_labels.get(tool_id, [])),
        )

        if tool_id not in self._reviews:
            self._reviews[tool_id] = []
        self._reviews[tool_id].append(review)
        self._save()

        avg = self._calc_avg(tool_id)
        logger.info(
            f"⭐ 評分提交: {tool_id} = {score}/5 by {reviewer} "
            f"(新均分: {avg:.2f}, 共 {len(self._reviews[tool_id])} 則)"
        )
        return True

    def add_security_label(self, tool_id: str, label: str) -> None:
        """為工具添加安全標籤 (如 ast_safe, hash_verified, bandit_clean)"""
        if tool_id not in self._security_labels:
            self._security_labels[tool_id] = []
        if label not in self._security_labels[tool_id]:
            self._security_labels[tool_id].append(label)
            self._save()
            logger.info(f"🏷️ 安全標籤: {tool_id} += [{label}]")

    def get_quality_report(self, tool_id: str) -> QualityReport:
        """取得工具品質報告"""
        reviews = self._reviews.get(tool_id, [])
        avg = self._calc_avg(tool_id)
        labels = self._security_labels.get(tool_id, [])

        return QualityReport(
            tool_id=tool_id,
            avg_score=avg,
            total_reviews=len(reviews),
            security_labels=labels,
            recent_reviews=reviews[-5:],  # 最近 5 則
        )

    def get_leaderboard(self, top_n: int = 10) -> List[QualityReport]:
        """取得品質排行榜"""
        reports = []
        for tool_id in self._reviews:
            report = self.get_quality_report(tool_id)
            # 至少 2 則評論才進入排行
            if report.total_reviews >= 2:
                reports.append(report)

        reports.sort(key=lambda r: r.avg_score, reverse=True)

        for i, r in enumerate(reports[:top_n]):
            r.rank = i + 1

        return reports[:top_n]

    def _calc_avg(self, tool_id: str) -> float:
        reviews = self._reviews.get(tool_id, [])
        if not reviews:
            return 0.0
        return sum(r.score for r in reviews) / len(reviews)

    def _load(self) -> None:
        """從磁碟載入評論"""
        try:
            if _REVIEWS_FILE.exists():
                data = json.loads(_REVIEWS_FILE.read_text(encoding="utf-8"))
                for tool_id, review_list in data.get("reviews", {}).items():
                    self._reviews[tool_id] = [Review(**r) for r in review_list]
                self._security_labels = data.get("security_labels", {})
        except Exception as e:
            logger.warning(f"⚠️ 載入評論資料失敗: {e}")

    def _save(self) -> None:
        """持久化評論到磁碟"""
        try:
            _REVIEWS_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "reviews": {
                    tid: [asdict(r) for r in reviews]
                    for tid, reviews in self._reviews.items()
                },
                "security_labels": self._security_labels,
            }
            _REVIEWS_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"❌ 儲存評論資料失敗: {e}")
