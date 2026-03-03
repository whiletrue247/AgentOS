"""
04_Engine — Event Trace (Observability 2.0)
=============================================
將 Engine 每步 emit() 的事件持久化到 SQLite，
支援事後回放 (Replay) 和記憶 Rollback。

功能：
  - 所有 EngineEvent 自動寫入 event_log.db
  - 按 session/時間查詢事件序列
  - 支援 Rollback 到指定 event_id

類似 LangSmith / LangFuse 的 Trace 功能，但完全本地化。
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EventTrace:
    """
    事件追蹤系統 (Observability 2.0)。
    
    將所有 Engine 事件持久化到 SQLite，
    支援事後查詢、回放和 Rollback。
    
    Args:
        db_path: SQLite 資料庫路徑
    """

    def __init__(self, db_path: str = "data/event_log.db"):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info(f"📊 EventTrace 初始化: {db_path}")

    def _init_db(self) -> None:
        """建立資料表"""
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS event_log (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    source_agent TEXT DEFAULT 'default',
                    target_agent TEXT,
                    payload TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_session 
                ON event_log(session_id, created_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_event_type 
                ON event_log(event_type)
            """)

    # ========================================
    # 寫入
    # ========================================

    def record(
        self,
        event_type: str,
        payload: Dict[str, Any],
        session_id: str = "default",
        source_agent: str = "default",
        target_agent: Optional[str] = None,
    ) -> str:
        """
        記錄一個事件。
        
        Args:
            event_type: 事件類型
            payload: 事件內容
            session_id: 會話 ID
            source_agent: 來源 Agent
            target_agent: 目標 Agent
            
        Returns:
            event_id
        """
        event_id = str(uuid.uuid4())
        now = datetime.now()

        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute(
                    """INSERT INTO event_log 
                       (id, session_id, event_type, source_agent, target_agent, 
                        payload, timestamp, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event_id, session_id, event_type,
                        source_agent, target_agent,
                        json.dumps(payload, ensure_ascii=False, default=str),
                        now.isoformat(), now.timestamp(),
                    ),
                )
        except Exception as e:
            logger.error(f"❌ EventTrace 寫入失敗: {e}")

        return event_id

    # ========================================
    # 查詢
    # ========================================

    def get_session_trace(
        self,
        session_id: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """取得指定 session 的完整事件序列"""
        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """SELECT * FROM event_log 
                       WHERE session_id = ? 
                       ORDER BY created_at ASC LIMIT ?""",
                    (session_id, limit),
                ).fetchall()
                return [self._row_to_dict(r) for r in rows]
        except Exception as e:
            logger.error(f"❌ EventTrace 查詢失敗: {e}")
            return []

    def get_recent_events(
        self,
        event_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """取得最近的事件"""
        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.row_factory = sqlite3.Row
                if event_type:
                    rows = conn.execute(
                        """SELECT * FROM event_log 
                           WHERE event_type = ?
                           ORDER BY created_at DESC LIMIT ?""",
                        (event_type, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """SELECT * FROM event_log 
                           ORDER BY created_at DESC LIMIT ?""",
                        (limit,),
                    ).fetchall()
                return [self._row_to_dict(r) for r in rows]
        except Exception as e:
            logger.error(f"❌ EventTrace 查詢失敗: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        """取得統計資訊"""
        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                total = conn.execute("SELECT COUNT(*) FROM event_log").fetchone()[0]
                sessions = conn.execute(
                    "SELECT COUNT(DISTINCT session_id) FROM event_log"
                ).fetchone()[0]
                types = conn.execute(
                    """SELECT event_type, COUNT(*) as cnt 
                       FROM event_log GROUP BY event_type 
                       ORDER BY cnt DESC"""
                ).fetchall()
                return {
                    "total_events": total,
                    "total_sessions": sessions,
                    "event_types": {t: c for t, c in types},
                }
        except Exception:
            return {"total_events": 0, "total_sessions": 0, "event_types": {}}

    # ========================================
    # Rollback
    # ========================================

    def get_rollback_point(self, event_id: str) -> Optional[Dict[str, Any]]:
        """取得指定 event_id 的事件資訊（用於 Rollback 參考）"""
        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM event_log WHERE id = ?", (event_id,)
                ).fetchone()
                return self._row_to_dict(row) if row else None
        except Exception:
            return None

    def delete_events_after(self, event_id: str, session_id: str) -> int:
        """
        刪除指定 event_id 之後的所有事件（Rollback）。
        
        Returns:
            刪除的事件數量
        """
        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                # 取得目標事件的時間戳
                row = conn.execute(
                    "SELECT created_at FROM event_log WHERE id = ?", (event_id,)
                ).fetchone()
                if not row:
                    return 0

                target_time = row[0]
                result = conn.execute(
                    """DELETE FROM event_log 
                       WHERE session_id = ? AND created_at > ?""",
                    (session_id, target_time),
                )
                deleted = result.rowcount
                logger.info(
                    f"⏪ Rollback: 刪除 {deleted} 個事件 (session={session_id}, "
                    f"after event={event_id[:8]}...)"
                )
                return deleted
        except Exception as e:
            logger.error(f"❌ Rollback 失敗: {e}")
            return 0

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        """將 sqlite3.Row 轉為 dict"""
        d = dict(row)
        if "payload" in d and isinstance(d["payload"], str):
            try:
                d["payload"] = json.loads(d["payload"])
            except json.JSONDecodeError:
                pass
        return d
