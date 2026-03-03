"""
02_Memory — Mem0 Hybrid Memory Provider (v5.0 SOTA)
=============================================================
透過 mem0.ai 整合非結構化記憶 (向量存儲 + 用戶長期記憶)。
提供與 GraphRAG 相輔相成的關聯檢索能力。
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

__all__ = ["Mem0Provider", "MEM0_AVAILABLE"]

logger = logging.getLogger(__name__)

try:
    from mem0 import Memory
    MEM0_AVAILABLE = True
except ImportError:
    MEM0_AVAILABLE = False
    logger.info("ℹ️ mem0 not installed — Mem0 provider fallback disabled")


class Mem0Provider:
    """整合 mem0 作為長期向量混合記憶提供者"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.memory = None

        if MEM0_AVAILABLE:
            try:
                chroma_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "mem0_chroma")
                os.makedirs(chroma_path, exist_ok=True)
                
                # Mem0 Config
                mem0_config = {
                    "vector_store": {
                        "provider": "chroma",
                        "config": {"collection_name": "agentos_mem0", "path": chroma_path}
                    }
                }
                self.memory = Memory.from_config(mem0_config)
                logger.info("🧠 Mem0Provider initialized successfully with Chroma backend.")
            except Exception as e:
                logger.warning(f"⚠️ Mem0 initialization failed: {e}")
                self.memory = None

    def add_memory(self, text: str, user_id: str = "default_user") -> bool:
        """將新事實或對話片段寫入 Mem0 長期記憶。"""
        if not self.memory:
            return False

        try:
            self.memory.add(text, user_id=user_id)
            logger.info(f"💾 Mem0: Added memory chunk for {user_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Mem0 add_memory failed: {e}")
            return False

    def search_memory(self, query: str, user_id: str = "default_user", limit: int = 5) -> str:
        """從 Mem0 檢索相關記憶並組裝回字串。"""
        if not self.memory:
            return ""

        try:
            # results typically returns a list of dictionaries with 'memory' key
            results = self.memory.search(query, user_id=user_id, limit=limit)
            if not results:
                return ""

            formatted = ["\n[Mem0 Vector Memory Context]:"]
            for r in results:
                # 確保相容不同版本 mem0 API，有時是回傳物件，有時是 dict
                mem_text = r.get("memory", str(r)) if isinstance(r, dict) else str(r)
                formatted.append(f"  - {mem_text}")

            logger.info(f"💡 Mem0: Retrieved {len(results)} memory entries")
            return "\n".join(formatted)
        except Exception as e:
            logger.error(f"❌ Mem0 search_memory failed: {e}")
            return ""
