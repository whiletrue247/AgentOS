"""
11_Sync_Handoff/handoff_manager.py
==================================
跨裝置 Agent 狀態接力管理器。
透過序列化 state 的 thread_id，並匯出 state checkpoint，可以將工作在不同設備或 Agent 間交接。
這裡我們實作一個基於 SQLite 的簡易 Checkpointer，並支援匯出打包狀態。
"""

import base64
import json
import logging
import sqlite3
import uuid
from typing import Any, Dict, Optional

from paths import get_data_dir

logger = logging.getLogger(__name__)

DB_PATH = get_data_dir() / "handoff_checkpoint.db"

class HandoffManager:
    """
    負責儲存、匯出與匯入 Agent 執行 Context。
    """
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(DB_PATH)
        self.local_device_id = str(uuid.uuid4())[:12]
        self._init_db()
        logger.info(f"📱 Handoff Manager initialized (Device: {self.local_device_id})")
        
    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS checkpoints (
                        thread_id TEXT PRIMARY KEY,
                        state_json TEXT NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to init Handoff DB: {e}")

    def save_checkpoint(self, thread_id: str, state_dict: Dict[str, Any]):
        """將 Agent 目前的完整狀態 (state_dict) 存入本地 DB"""
        try:
            # 去除可能無法序列化的物件 (例如 langgraph 的某些特殊 class，須轉為 dict/str)
            # 在這裡假設 state_dict 已經可以被 json.dumps (如 dict 包含 {"messages": [{"role":"user","content":"..."}]})
            state_str = json.dumps(state_dict, ensure_ascii=False)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO checkpoints (thread_id, state_json, updated_at) 
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """, (thread_id, state_str))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to save checkpoint for {thread_id}: {e}")

    def load_checkpoint(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """從本地 DB 恢復 Agent 狀態"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT state_json FROM checkpoints WHERE thread_id=?", (thread_id,))
                row = cursor.fetchone()
                if row:
                    return json.loads(row[0])
        except Exception as e:
            logger.error(f"Failed to load checkpoint for {thread_id}: {e}")
        return None

    def export_session_state(self, thread_id: str) -> Optional[str]:
        """ 
        將當前任務狀態打包，產生交接 URI (例如放入 QR Code)。
        實戰中這適合跨設備同步 (Mobile <-> PC)。
        """
        state_dict = self.load_checkpoint(thread_id)
        if not state_dict:
            logger.warning(f"No checkpoint found for thread {thread_id} to export.")
            return None

        payload = {
            "version": "1.1",
            "source_device": self.local_device_id,
            "thread_id": thread_id,
            "state_snapshot": state_dict,
        }
        
        # 轉成 base64 模擬打包
        json_str = json.dumps(payload, ensure_ascii=False)
        base64_payload = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")
        
        handoff_uri = f"agentos://handoff?payload={base64_payload}"
        logger.info(f"🔄 產生 Handoff URI 成功 (Thread: {thread_id})。長度: {len(handoff_uri)} bytes")
        return handoff_uri
        
    def import_session_state(self, handoff_uri: str) -> Optional[str]:
        """ 
        接收來自其他裝置的接力 URI，解密並還原寫入本地 DB。
        回傳 thread_id，方便接續執行。
        """
        try:
            if not handoff_uri.startswith("agentos://handoff?payload="):
                logger.error("❌ 無效的 Handoff URI 格式")
                return None
                
            base64_payload = handoff_uri.split("payload=")[1]
            json_str = base64.b64decode(base64_payload).decode("utf-8")
            payload = json.loads(json_str)
            
            source_device = payload.get("source_device", "Unknown")
            thread_id = payload.get("thread_id", "Unknown")
            state_dict = payload.get("state_snapshot", {})
            
            # 將收到的狀態寫入本地 Checkpoint DB
            self.save_checkpoint(thread_id, state_dict)
            
            logger.info(f"✅ 成功接力！來自裝置 {source_device} 的任務 (Thread: {thread_id})")
            return thread_id
            
        except Exception as e:
            logger.error(f"❌ 狀態接力還原失敗: {e}")
            return None
