"""
02_Memory — Chroma 向量記憶 Provider
=====================================
基於 ChromaDB 的 MemoryProvider 實作，提供語意向量檢索。
優於 BM25 的場景：模糊語意查詢、跨語言檢索、相似記憶聚合。

依賴：
  pip install chromadb sentence-transformers

當 chromadb 未安裝時，此模組不可用，MemoryManager 應使用 SQLite fallback。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

try:
    from contracts.interfaces import MemoryProvider, UnifiedMemoryItem
except ImportError:
    from interfaces import MemoryProvider, UnifiedMemoryItem


class ChromaMemoryProvider:
    """
    基於 ChromaDB 的向量記憶 Provider。
    
    使用 sentence-transformers 將記憶內容轉為 embedding，
    支援語意相似度搜尋 (cosine similarity)。
    
    Args:
        persist_dir: ChromaDB 持久化目錄
        collection_name: 集合名稱
        embedding_model: sentence-transformers 模型名稱
    """

    def __init__(
        self,
        persist_dir: str = "data/chroma",
        collection_name: str = "agent_memory",
        embedding_model: str = "all-MiniLM-L6-v2",
    ):
        if not CHROMA_AVAILABLE:
            raise ImportError(
                "chromadb is required: pip install chromadb sentence-transformers"
            )

        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._embedding_model_name = embedding_model
        logger.info(
            f"🧠 ChromaMemoryProvider 初始化: "
            f"dir={persist_dir}, collection={collection_name}, "
            f"model={embedding_model}"
        )

    # ========================================
    # MemoryProvider 介面實作
    # ========================================

    async def write(self, item: UnifiedMemoryItem) -> None:
        """寫入或更新一條記憶 (upsert)"""
        metadata = {
            "content_type": item.content_type,
            "importance": item.importance,
            "t_created": item.t_created.isoformat(),
            "access_count": item.metadata.get("access_count", 0),
        }
        # 合併自定義 metadata
        for k, v in item.metadata.items():
            if isinstance(v, (str, int, float, bool)):
                metadata[k] = v

        self._collection.upsert(
            ids=[item.memory_id],
            documents=[item.content],
            metadatas=[metadata],
        )

    async def read(self, memory_id: str) -> Optional[UnifiedMemoryItem]:
        """根據 ID 精確讀取"""
        try:
            result = self._collection.get(ids=[memory_id], include=["documents", "metadatas"])
            if not result["ids"]:
                return None
            return self._result_to_item(
                result["ids"][0],
                result["documents"][0],
                result["metadatas"][0],
            )
        except Exception:
            return None

    async def search(
        self,
        query: str,
        top_k: int = 5,
        min_importance: float = 0.0,
        content_type: Optional[str] = None,
    ) -> list[UnifiedMemoryItem]:
        """語意向量搜尋"""
        where_filter = {}
        if min_importance > 0:
            where_filter["importance"] = {"$gte": min_importance}
        if content_type:
            where_filter["content_type"] = content_type

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where_filter if where_filter else None,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.error(f"❌ Chroma search failed: {e}")
            return []

        items = []
        if results["ids"] and results["ids"][0]:
            for i, mid in enumerate(results["ids"][0]):
                item = self._result_to_item(
                    mid,
                    results["documents"][0][i],
                    results["metadatas"][0][i],
                )
                items.append(item)

        return items

    async def delete(self, memory_id: str) -> bool:
        """刪除一條記憶"""
        try:
            self._collection.delete(ids=[memory_id])
            return True
        except Exception:
            return False

    async def list_by_tags(self, tags: list[str], top_k: int = 10) -> list[UnifiedMemoryItem]:
        """根據 tags 列出記憶 (使用 metadata 過濾)"""
        # ChromaDB 不直接支援 list tag 過濾，用第一個 tag 做 where
        if not tags:
            return []
        try:
            results = self._collection.get(
                where={"custom_tags": {"$eq": tags[0]}} if len(tags) == 1 else None,
                limit=top_k,
                include=["documents", "metadatas"],
            )
            return [
                self._result_to_item(results["ids"][i], results["documents"][i], results["metadatas"][i])
                for i in range(len(results["ids"]))
            ]
        except Exception:
            return []

    # ========================================
    # 內部工具
    # ========================================

    @staticmethod
    def _result_to_item(memory_id: str, content: str, metadata: dict) -> UnifiedMemoryItem:
        """將 Chroma 結果轉為 UnifiedMemoryItem"""
        return UnifiedMemoryItem(
            memory_id=memory_id,
            content=content,
            content_type=metadata.get("content_type", "fact"),
            importance=metadata.get("importance", 0.5),
            t_created=datetime.fromisoformat(metadata.get("t_created", datetime.now().isoformat())),
            metadata={k: v for k, v in metadata.items() if k not in ("content_type", "importance", "t_created")},
        )
