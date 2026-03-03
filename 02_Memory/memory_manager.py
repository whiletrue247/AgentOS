"""
02_Memory — 統一記憶管理器
==========================
所有記憶操作的統一入口。
MemoryManager 不直接操作資料庫，而是委派給 MemoryProvider 實作。
上層模組（Engine、Tool System）只需呼叫 MemoryManager，無需關心後端。

架構：
  MemoryManager
    ├── provider: MemoryProvider (SQLite / PgVector / Obsidian)
    └── bm25_index: BM25Index (可選的本地文字檢索加速)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from contracts.interfaces import MemoryProvider, UnifiedMemoryItem

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    統一記憶管理器。
    所有讀寫記憶的操作都經過這裡。
    """

    def __init__(self, provider: MemoryProvider):
        self._provider = provider
        self._bm25_index: Optional[Any] = None  # 延遲載入 BM25Index

    @property
    def provider(self) -> MemoryProvider:
        return self._provider

    def set_provider(self, provider: MemoryProvider) -> None:
        """熱切換 Provider（換資料庫 = 換 Provider）"""
        logger.info(f"🔄 Memory Provider 切換為: {type(provider).__name__}")
        self._provider = provider
        # 重建 BM25 索引
        self._bm25_index = None

    # ========================================
    # CRUD 操作
    # ========================================

    async def remember(
        self,
        content: str,
        content_type: str = "fact",
        importance: float = 0.5,
        metadata: Optional[dict[str, Any]] = None,
        relationships: Optional[list[str]] = None,
    ) -> UnifiedMemoryItem:
        """
        寫入一條新記憶。
        自動生成 memory_id 和時間戳。
        """
        item = UnifiedMemoryItem(
            memory_id=str(uuid.uuid4()),
            content=content,
            content_type=content_type,
            importance=importance,
            t_created=datetime.now(),
            relationships=relationships or [],
            metadata=metadata or {},
        )
        await self._provider.write(item)
        logger.debug(f"💾 記憶已寫入: [{item.content_type}] {item.content[:50]}...")
        return item

    async def recall(self, memory_id: str) -> Optional[UnifiedMemoryItem]:
        """根據 ID 精確讀取一條記憶"""
        return await self._provider.read(memory_id)

    async def search(
        self,
        query: str,
        top_k: int = 5,
        min_importance: float = 0.0,
        content_type: Optional[str] = None,
    ) -> list[UnifiedMemoryItem]:
        """
        搜索記憶。
        委派給 Provider 的 search 方法（由 Provider 決定用 BM25 或向量）。
        """
        results = await self._provider.search(
            query=query,
            top_k=top_k,
            min_importance=min_importance,
            content_type=content_type,
        )
        logger.debug(f"🔍 搜索 '{query}' → 找到 {len(results)} 條記憶")
        return results

    async def forget(self, memory_id: str) -> bool:
        """刪除一條記憶"""
        success = await self._provider.delete(memory_id)
        if success:
            logger.debug(f"🗑️ 記憶已刪除: {memory_id}")
        return success

    async def update(self, item: UnifiedMemoryItem) -> None:
        """更新一條記憶（覆寫）"""
        await self._provider.write(item)
        logger.debug(f"📝 記憶已更新: {item.memory_id}")

    # ========================================
    # 高階操作
    # ========================================

    async def remember_preference(
        self,
        preference_key: str,
        preference_value: str,
        agent_id: str = "default",
    ) -> UnifiedMemoryItem:
        """
        記錄使用者偏好（行為反饋學習迴路的入口）。
        自動標記 content_type="preference" 並加上 agent_id tag。
        """
        return await self.remember(
            content=f"{preference_key}: {preference_value}",
            content_type="preference",
            importance=0.8,
            metadata={
                "custom_tags": [f"agent:{agent_id}", "preference"],
                "preference_signal": {
                    "key": preference_key,
                    "value": preference_value,
                },
            },
        )

    async def get_agent_memories(
        self,
        agent_id: str,
        top_k: int = 10,
    ) -> list[UnifiedMemoryItem]:
        """
        取得特定 Agent 的私有記憶。
        透過 metadata.custom_tags 中的 agent:{id} 過濾。
        """
        return await self._provider.list_by_tags(
            tags=[f"agent:{agent_id}"],
            top_k=top_k,
        )

    async def get_relevant_context(
        self,
        query: str,
        agent_id: str = "default",
        max_tokens_hint: int = 2000,
    ) -> str:
        """
        為 Engine 組裝「相關記憶上下文」。
        搜索最相關的記憶，拼接成一段文字，供注入 System Prompt。

        max_tokens_hint: 大致的 Token 限制（用字元數近似，1 Token ≈ 4 chars EN / 1.5 chars CJK）
        """
        memories = await self.search(query=query, top_k=10, min_importance=0.3)

        # 按 importance 降序排列
        memories.sort(key=lambda m: m.importance, reverse=True)

        lines: list[str] = []
        char_count = 0
        char_limit = max_tokens_hint * 3  # 粗估

        for mem in memories:
            line = f"[{mem.content_type}] {mem.content}"
            if char_count + len(line) > char_limit:
                break
            lines.append(line)
            char_count += len(line)

        if not lines:
            return ""

        return "--- Agent Memory Context ---\n" + "\n".join(lines) + "\n--- End Memory Context ---"

    # ========================================
    # 自動遺忘 (Time-based Decay)
    # ========================================

    async def run_decay_cycle(
        self,
        half_life_days: float = 7.0,
        min_importance: float = 0.05,
        max_scan: int = 100,
    ) -> int:
        """
        執行記憶衰減週期（自動遺忘）。
        
        公式與 KG apply_decay() 一致：
          new_importance = importance * 0.5^(days_since_created / half_life_days)
        importance 低於 min_importance 的記憶會被刪除。
        
        Args:
            half_life_days: 半衰期（天）
            min_importance: 最低重要性門檻
            max_scan: 每次最多掃描幾條記憶
            
        Returns:
            被遺忘（刪除）的記憶數量
        """
        import math

        now = datetime.now()
        forgotten = 0

        try:
            # 掃描低重要性記憶
            candidates = await self._provider.search(
                query="*",
                top_k=max_scan,
                min_importance=0.0,
            )

            for mem in candidates:
                days_age = (now - mem.t_created).total_seconds() / 86400.0
                if days_age <= 0:
                    continue

                # 計算衰減後的重要性
                decayed = mem.importance * math.pow(0.5, days_age / half_life_days)

                if decayed < min_importance:
                    await self._provider.delete(mem.memory_id)
                    forgotten += 1
                    logger.debug(
                        f"🗑️ 記憶衰減遺忘: {mem.content[:30]}... "
                        f"(importance {mem.importance:.2f} → {decayed:.4f})"
                    )

        except Exception as e:
            logger.error(f"❌ 記憶衰減週期失敗: {e}")

        if forgotten > 0:
            logger.info(f"🧹 記憶衰減週期完成: 遺忘 {forgotten} 條記憶")

        return forgotten
