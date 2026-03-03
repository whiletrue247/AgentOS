"""
04_Engine/audit_trail.py
========================
完整的 Audit Trail Logger，用於記錄所有 Agent 的敏感操作。
資料以 SQLite 持久化，並提供 Markdown 格式的歷史匯出功能。
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import sqlite3
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from paths import get_data_dir

__all__ = ["AuditTrail", "AuditEntry", "get_audit_trail"]

logger = logging.getLogger(__name__)

@dataclass
class AuditEntry:
    id: int
    timestamp: str
    agent_id: str
    action_type: str
    payload: str
    payload_hash: str
    result_status: str
    risk_level: str
    execution_time_ms: int

class AuditTrail:
    """SQLite-backed Audit Trail for Agent actions."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize the Audit Trail database."""
        if db_path is None:
            db_path = str(get_data_dir() / "audit_trail.db")
            
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Create the audit table if it does not exist."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS audit_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        agent_id TEXT NOT NULL,
                        action_type TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        payload_hash TEXT NOT NULL,
                        result_status TEXT NOT NULL,
                        risk_level TEXT NOT NULL,
                        execution_time_ms INTEGER NOT NULL
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_id ON audit_log(agent_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON audit_log(timestamp)")
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize audit DB at {self.db_path}: {e}")

    def log_action(
        self,
        agent_id: str,
        action_type: str,
        payload: str | Dict[str, Any],
        result_status: str,
        risk_level: str = "low",
        execution_time_ms: int = 0
    ) -> None:
        """
        Log an agent action to the audit trail.
        
        Args:
            agent_id: The ID or role of the agent performing the action.
            action_type: e.g., 'shell', 'api_call', 'file_write'.
            payload: The command, code, or data being executed.
            result_status: 'success', 'blocked', 'failed', 'timeout'.
            risk_level: 'low', 'medium', 'high', 'critical'.
            execution_time_ms: Time taken for the action.
        """
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        if isinstance(payload, dict):
            payload_str = json.dumps(payload, ensure_ascii=False)
        else:
            payload_str = str(payload)
            
        payload_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO audit_log 
                    (timestamp, agent_id, action_type, payload, payload_hash, result_status, risk_level, execution_time_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (timestamp, agent_id, action_type, payload_str, payload_hash, result_status, risk_level, execution_time_ms))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to log audit action: {e}")

    def get_history(self, agent_id: Optional[str] = None, limit: int = 100) -> List[AuditEntry]:
        """Retrieve recent audit history, optionally filtered by agent_id."""
        entries = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                if agent_id:
                    cursor.execute("""
                        SELECT * FROM audit_log 
                        WHERE agent_id = ? 
                        ORDER BY timestamp DESC LIMIT ?
                    """, (agent_id, limit))
                else:
                    cursor.execute("""
                        SELECT * FROM audit_log 
                        ORDER BY timestamp DESC LIMIT ?
                    """, (limit,))
                    
                rows = cursor.fetchall()
                for r in rows:
                    entries.append(AuditEntry(
                        id=r["id"],
                        timestamp=r["timestamp"],
                        agent_id=r["agent_id"],
                        action_type=r["action_type"],
                        payload=r["payload"],
                        payload_hash=r["payload_hash"],
                        result_status=r["result_status"],
                        risk_level=r["risk_level"],
                        execution_time_ms=r["execution_time_ms"]
                    ))
        except Exception as e:
            logger.error(f"Failed to retrieve audit history: {e}")
            
        return entries

    def export_report(self, days: int = 7) -> str:
        """Export a Markdown report of actions in the last N days."""
        cutoff_date = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat()
        
        report = [f"# AgentOS Audit Report (Last {days} days)", ""]
        report.append(f"Generated at: {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
        report.append("")
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Summary Stats
                cursor.execute("""
                    SELECT result_status, COUNT(*) as count 
                    FROM audit_log 
                    WHERE timestamp >= ? 
                    GROUP BY result_status
                """, (cutoff_date,))
                stats = cursor.fetchall()
                
                report.append("## Summary by Status")
                for s in stats:
                    report.append(f"- **{s['result_status']}**: {s['count']} actions")
                report.append("")
                
                # High Risk Actions
                cursor.execute("""
                    SELECT timestamp, agent_id, action_type, result_status 
                    FROM audit_log 
                    WHERE timestamp >= ? AND risk_level IN ('high', 'critical')
                    ORDER BY timestamp DESC
                """, (cutoff_date,))
                high_risk = cursor.fetchall()
                
                report.append("## High Risk Actions")
                if not high_risk:
                    report.append("*No high-risk actions recorded.*")
                else:
                    report.append("| Timestamp | Agent | Action | Status |")
                    report.append("|-----------|-------|--------|--------|")
                    for r in high_risk:
                        report.append(f"| {r['timestamp'][:19]} | {r['agent_id']} | {r['action_type']} | {r['result_status']} |")
                        
        except Exception as e:
            report.append(f"\n*Error generating report: {e}*")
            
        return "\n".join(report)

# Thread-safe singleton
_audit_trail_instance: Optional[AuditTrail] = None
_audit_trail_lock = threading.Lock()

def get_audit_trail() -> AuditTrail:
    """Get the thread-safe singleton AuditTrail instance."""
    global _audit_trail_instance
    if _audit_trail_instance is None:
        with _audit_trail_lock:
            # Double-checked locking
            if _audit_trail_instance is None:
                _audit_trail_instance = AuditTrail()
    return _audit_trail_instance
