"""
SQLite Memory Provider
======================
MemoryProvider 的 SQLite 實作。
零依賴（sqlite3 是 Python 標準庫），適合單機部署。
使用 FTS5 做全文檢索（等同於本地 BM25）。
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from contracts.interfaces import MemoryProvider, UnifiedMemoryItem

logger = logging.getLogger(__name__)

# 日期格式
_DT_FMT = "%Y-%m-%dT%H:%M:%S.%f"


def _dt_to_str(dt: Optional[datetime]) -> Optional[str]:
    return dt.strftime(_DT_FMT) if dt else None


def _str_to_dt(s: Optional[str]) -> Optional[datetime]:
    return datetime.strptime(s, _DT_FMT) if s else None


class SQLiteMemoryProvider:
    """
    基於 SQLite + FTS5 的 MemoryProvider。
    FTS5 是 SQLite 內建的全文檢索引擎，底層使用 BM25 排序。
    """

    def __init__(self, db_path: str = "./memory.db"):
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()
        logger.info(f"💾 SQLite Memory Provider 已啟動: {db_path}")

    def _init_tables(self) -> None:
        cur = self._conn.cursor()

        # 主表
        cur.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                memory_id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                content_type TEXT NOT NULL DEFAULT 'fact',
                importance REAL NOT NULL DEFAULT 0.5,
                t_created TEXT NOT NULL,
                t_valid TEXT,
                t_invalid TEXT,
                relationships TEXT DEFAULT '[]',
                embedding BLOB,
                provider_hint TEXT,
                metadata TEXT DEFAULT '{}'
            )
        """)

        # FTS5 全文檢索索引（BM25 排序）
        cur.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                memory_id,
                content,
                content_type,
                content='memories',
                content_rowid='rowid'
            )
        """)

        # 觸發器：主表寫入/更新/刪除時同步 FTS
        cur.executescript("""
            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(memory_id, content, content_type)
                VALUES (new.memory_id, new.content, new.content_type);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, memory_id, content, content_type)
                VALUES ('delete', old.memory_id, old.content, old.content_type);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, memory_id, content, content_type)
                VALUES ('delete', old.memory_id, old.content, old.content_type);
                INSERT INTO memories_fts(memory_id, content, content_type)
                VALUES (new.memory_id, new.content, new.content_type);
            END;
        """)

        self._conn.commit()

    def _row_to_item(self, row: sqlite3.Row) -> UnifiedMemoryItem:
        return UnifiedMemoryItem(
            memory_id=row["memory_id"],
            content=row["content"],
            content_type=row["content_type"],
            importance=row["importance"],
            t_created=_str_to_dt(row["t_created"]) or datetime.now(),
            t_valid=_str_to_dt(row["t_valid"]),
            t_invalid=_str_to_dt(row["t_invalid"]),
            relationships=json.loads(row["relationships"]),
            embedding=None,  # SQLite 不做向量
            provider_hint="sqlite",
            metadata=json.loads(row["metadata"]),
        )

    # ========================================
    # MemoryProvider 介面實作
    # ========================================

    async def write(self, item: UnifiedMemoryItem) -> None:
        cur = self._conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO memories
            (memory_id, content, content_type, importance,
             t_created, t_valid, t_invalid,
             relationships, provider_hint, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item.memory_id,
            item.content,
            item.content_type,
            item.importance,
            _dt_to_str(item.t_created),
            _dt_to_str(item.t_valid),
            _dt_to_str(item.t_invalid),
            json.dumps(item.relationships),
            item.provider_hint or "sqlite",
            json.dumps(item.metadata),
        ))
        self._conn.commit()

    async def read(self, memory_id: str) -> Optional[UnifiedMemoryItem]:
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM memories WHERE memory_id = ?", (memory_id,))
        row = cur.fetchone()
        return self._row_to_item(row) if row else None

    async def search(
        self,
        query: str,
        top_k: int = 5,
        min_importance: float = 0.0,
        content_type: Optional[str] = None,
    ) -> list[UnifiedMemoryItem]:
        """使用 FTS5 BM25 全文檢索"""
        cur = self._conn.cursor()

        # FTS5 搜索，用 bm25() 排序
        sql = """
            SELECT m.*, bm25(memories_fts) AS rank
            FROM memories_fts fts
            JOIN memories m ON m.memory_id = fts.memory_id
            WHERE memories_fts MATCH ?
              AND m.importance >= ?
        """
        params: list = [query, min_importance]

        if content_type:
            sql += " AND m.content_type = ?"
            params.append(content_type)

        sql += " ORDER BY rank LIMIT ?"
        params.append(top_k)

        try:
            cur.execute(sql, params)
            return [self._row_to_item(row) for row in cur.fetchall()]
        except sqlite3.OperationalError:
            # FTS 語法錯誤時 fallback 到 LIKE
            logger.warning(f"⚠️ FTS5 搜索失敗，降級到 LIKE 搜索: {query}")
            return await self._search_like(query, top_k, min_importance, content_type)

    async def _search_like(
        self, query: str, top_k: int, min_importance: float, content_type: Optional[str]
    ) -> list[UnifiedMemoryItem]:
        """FTS 失敗時的降級搜索"""
        cur = self._conn.cursor()
        sql = "SELECT * FROM memories WHERE content LIKE ? AND importance >= ?"
        params: list = [f"%{query}%", min_importance]
        if content_type:
            sql += " AND content_type = ?"
            params.append(content_type)
        sql += " ORDER BY importance DESC LIMIT ?"
        params.append(top_k)
        cur.execute(sql, params)
        return [self._row_to_item(row) for row in cur.fetchall()]

    async def delete(self, memory_id: str) -> bool:
        cur = self._conn.cursor()
        cur.execute("DELETE FROM memories WHERE memory_id = ?", (memory_id,))
        self._conn.commit()
        return cur.rowcount > 0

    async def list_by_tags(self, tags: list[str], top_k: int = 10) -> list[UnifiedMemoryItem]:
        """透過 JSON 的 metadata.custom_tags 過濾"""
        cur = self._conn.cursor()
        # SQLite 的 json_each 可以展開 JSON 陣列
        # 但為了相容性，用 LIKE 做簡單匹配
        results: list[UnifiedMemoryItem] = []
        for tag in tags:
            cur.execute(
                "SELECT * FROM memories WHERE metadata LIKE ? ORDER BY importance DESC",
                (f"%{tag}%",),
            )
            for row in cur.fetchall():
                item = self._row_to_item(row)
                if item.memory_id not in [r.memory_id for r in results]:
                    results.append(item)
                    if len(results) >= top_k:
                        return results
        return results

    def close(self) -> None:
        self._conn.close()

    def __del__(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass
