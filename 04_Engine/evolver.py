"""
04_Engine — Soul Evolver (Memory → SOUL 自動畢業)
==================================================
定期掃描 Memory 中高頻/高重要性的事實記憶，
當滿足畢業條件時，將知識「畢業」到 SOUL.md 的 Learned Patterns 區塊。

設計原則：
  - 規則式畢業（importance ≥ threshold 且 access ≥ N）
  - 首次實作必須有人類確認門檻（防止噪音污染 SOUL）
  - SOUL.md 備份機制（.bak）
  - 可由 LoRATunerSchedule 或獨立排程呼叫

靈感來源：Voyager (Minecraft Agent) 的 Skill Library 自我進化機制。
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


# ============================================================
# Graduation Candidate
# ============================================================

@dataclass
class GraduationCandidate:
    """一條可能畢業到 SOUL 的記憶"""
    memory_id: str
    content: str
    content_type: str
    importance: float
    access_count: int
    created_at: datetime
    source: str = "memory"  # memory | kg | conversation


# ============================================================
# Soul Evolver
# ============================================================

class SoulEvolver:
    """
    Memory → SOUL 自動畢業引擎。
    
    掃描高頻/高重要性記憶，經人類確認後追加到 SOUL.md。
    
    Args:
        soul_path: SOUL.md 檔案路徑
        memory_manager: MemoryManager 實例
        importance_threshold: 重要性門檻 (0.0~1.0)
        min_access_count: 最少存取次數
        auto_graduate: 是否自動畢業（無人類確認）
        max_candidates_per_cycle: 每次最多處理幾筆候選
    """

    def __init__(
        self,
        soul_path: str = "SOUL.md",
        memory_manager: Any = None,
        importance_threshold: float = 0.8,
        min_access_count: int = 5,
        auto_graduate: bool = False,
        max_candidates_per_cycle: int = 5,
    ):
        self.soul_path = Path(soul_path)
        self._memory = memory_manager
        self.importance_threshold = importance_threshold
        self.min_access_count = min_access_count
        self.auto_graduate = auto_graduate
        self.max_candidates_per_cycle = max_candidates_per_cycle

        # 畢業歷史紀錄 (防止重複畢業)
        self._graduated_ids: set[str] = set()
        self._load_graduated_ids()

        logger.info(
            f"🎓 SoulEvolver 初始化: threshold={importance_threshold}, "
            f"min_access={min_access_count}, auto={auto_graduate}"
        )

    # ========================================
    # 掃描候選
    # ========================================

    async def scan_candidates(self) -> List[GraduationCandidate]:
        """
        掃描 Memory 中符合畢業條件的記憶。
        
        Returns:
            符合條件的畢業候選列表
        """
        if not self._memory:
            logger.warning("⚠️ SoulEvolver: 未注入 MemoryManager，無法掃描")
            return []

        candidates: List[GraduationCandidate] = []

        try:
            # 搜尋高重要性的事實型記憶
            items = await self._memory.search(
                query="*",
                top_k=50,
                min_importance=self.importance_threshold,
                content_type="fact",
            )

            for item in items:
                # 跳過已畢業的記憶
                if item.memory_id in self._graduated_ids:
                    continue

                # 檢查存取次數
                access_count = item.metadata.get("access_count", 0)
                if access_count < self.min_access_count:
                    continue

                candidates.append(GraduationCandidate(
                    memory_id=item.memory_id,
                    content=item.content,
                    content_type=item.content_type,
                    importance=item.importance,
                    access_count=access_count,
                    created_at=item.t_created,
                    source=item.metadata.get("source", "memory"),
                ))

        except Exception as e:
            logger.error(f"❌ SoulEvolver scan 失敗: {e}")

        # 按重要性排序，取前 N 個
        candidates.sort(key=lambda c: (c.importance, c.access_count), reverse=True)
        candidates = candidates[:self.max_candidates_per_cycle]

        logger.info(f"🔍 掃描到 {len(candidates)} 個畢業候選")
        return candidates

    # ========================================
    # 格式化畢業內容
    # ========================================

    @staticmethod
    def format_graduation(candidates: List[GraduationCandidate]) -> str:
        """
        將候選記憶格式化為 SOUL.md 的 Learned Patterns 格式。
        
        Args:
            candidates: 畢業候選列表
            
        Returns:
            格式化後的 markdown 文字
        """
        if not candidates:
            return ""

        lines = [
            "",
            f"<!-- Graduated by SoulEvolver at {datetime.now().strftime('%Y-%m-%d %H:%M')} -->",
        ]

        for c in candidates:
            # 格式: - [Learned] 內容 (importance: X, accessed: N times)
            lines.append(
                f"- **[Learned]** {c.content} "
                f"_(importance: {c.importance:.2f}, accessed: {c.access_count}x, "
                f"source: {c.source})_"
            )

        return "\n".join(lines)

    # ========================================
    # 預覽變更 (Human-in-the-Loop)
    # ========================================

    def preview_changes(self, candidates: List[GraduationCandidate]) -> bool:
        """
        顯示畢業候選供人類確認。
        
        Args:
            candidates: 畢業候選列表
            
        Returns:
            True = 批准畢業, False = 拒絕
        """
        import sys

        if self.auto_graduate:
            logger.info("🤖 auto_graduate=True，自動批准畢業")
            return True

        if not sys.stdin.isatty():
            logger.warning("⚠️ 非互動環境，拒絕自動畢業")
            return False

        print("\n" + "=" * 60)
        print("🎓 SoulEvolver — 以下記憶即將畢業到 SOUL.md:")
        print("=" * 60)

        for i, c in enumerate(candidates, 1):
            print(f"\n  [{i}] {c.content}")
            print(f"      importance={c.importance:.2f}, 存取={c.access_count}次, 來源={c.source}")

        print("\n" + "=" * 60)
        print("這些模式將永久寫入您的 AI 人格 (SOUL.md)。")

        while True:
            try:
                ans = input("確認畢業? [y/n] ").strip().lower()
                if ans in ("y", "yes"):
                    return True
                elif ans in ("n", "no"):
                    return False
                else:
                    print("請輸入 y 或 n。")
            except (KeyboardInterrupt, EOFError):
                return False

    # ========================================
    # 執行畢業 (寫入 SOUL.md)
    # ========================================

    def graduate(self, candidates: List[GraduationCandidate]) -> int:
        """
        將候選記憶寫入 SOUL.md。
        
        Args:
            candidates: 已批准的畢業候選
            
        Returns:
            成功畢業的數量
        """
        if not candidates:
            return 0

        # 1. 備份 SOUL.md
        if self.soul_path.exists():
            backup_path = self.soul_path.with_suffix(".md.bak")
            shutil.copy2(str(self.soul_path), str(backup_path))
            logger.info(f"💾 SOUL.md 已備份至 {backup_path}")

        # 2. 讀取現有內容
        if self.soul_path.exists():
            content = self.soul_path.read_text(encoding="utf-8")
        else:
            content = "# SOUL\n"

        # 3. 尋找或建立 Learned Patterns 區塊
        section_header = "## Learned Patterns"
        if section_header not in content:
            content += f"\n\n{section_header}\n"

        # 4. 追加畢業內容
        graduation_text = self.format_graduation(candidates)
        
        # 插入到 ## Learned Patterns 區塊的末尾
        insert_pos = content.find(section_header) + len(section_header)
        # 跳過 section header 後的換行
        while insert_pos < len(content) and content[insert_pos] == '\n':
            insert_pos += 1
        
        # 找到下一個 ## 區塊的位置（如果有的話）
        next_section = content.find("\n## ", insert_pos)
        if next_section == -1:
            # 沒有下一個區塊，追加到末尾
            content += graduation_text + "\n"
        else:
            # 在下一個區塊前插入
            content = content[:next_section] + graduation_text + "\n" + content[next_section:]

        # 5. 寫入
        self.soul_path.write_text(content, encoding="utf-8")

        # 6. 記錄已畢業的 ID
        for c in candidates:
            self._graduated_ids.add(c.memory_id)
        self._save_graduated_ids()

        logger.info(f"🎓 成功畢業 {len(candidates)} 條記憶到 SOUL.md")
        return len(candidates)

    # ========================================
    # 完整進化週期
    # ========================================

    async def run_cycle(self) -> int:
        """
        執行一次完整的進化週期：掃描 → 預覽 → 畢業。
        
        Returns:
            本次畢業的記憶數量
        """
        logger.info("🔄 SoulEvolver: 開始進化週期")

        # 1. 掃描候選
        candidates = await self.scan_candidates()
        if not candidates:
            logger.info("ℹ️ 本次週期無畢業候選")
            return 0

        # 2. 人類確認（或自動批准）
        approved = self.preview_changes(candidates)
        if not approved:
            logger.info("🚫 人類拒絕本次畢業")
            return 0

        # 3. 執行畢業
        count = self.graduate(candidates)
        return count

    # ========================================
    # 畢業 ID 持久化
    # ========================================

    def _load_graduated_ids(self) -> None:
        """從檔案載入已畢業的 memory_id 集合"""
        id_file = self.soul_path.parent / ".soul_graduated_ids"
        if id_file.exists():
            try:
                self._graduated_ids = set(
                    id_file.read_text(encoding="utf-8").strip().splitlines()
                )
            except Exception:
                self._graduated_ids = set()

    def _save_graduated_ids(self) -> None:
        """將已畢業的 memory_id 集合儲存到檔案"""
        id_file = self.soul_path.parent / ".soul_graduated_ids"
        try:
            id_file.write_text(
                "\n".join(sorted(self._graduated_ids)),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"⚠️ 無法儲存畢業 ID 列表: {e}")
