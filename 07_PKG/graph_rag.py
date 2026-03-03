"""
07_PKG — GraphRAG Hybrid Retriever (v5.0 SOTA)
=================================================
結合知識圖譜 (KG) 與 LLM 結構化擷取，實現：
  1. ingest_memory() — 從對話文本自動抽取 RDF 三元組存入 KG
  2. retrieve_context() — 從使用者查詢中抽取實體，召回圖譜上下文

使用 LLM Structured Output (JSON Mode) 進行真實 NER，而非 if/else 硬編碼。
"""

from __future__ import annotations

import json
import logging
from typing import Any, List

logger = logging.getLogger(__name__)

try:
    from .knowledge_graph import PersonalKnowledgeGraph
except ImportError:
    from knowledge_graph import PersonalKnowledgeGraph

# 嘗試動態載入 Mem0Provider
try:
    import importlib.util
    import sys
    import os
    mem0_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../02_Memory_Context/mem0_provider.py"))
    spec = importlib.util.spec_from_file_location("mem0_provider", mem0_path)
    mem0_module = importlib.util.module_from_spec(spec)
    sys.modules["mem0_provider"] = mem0_module
    spec.loader.exec_module(mem0_module)
    Mem0Provider = getattr(mem0_module, "Mem0Provider", None)
except Exception:
    Mem0Provider = None


class GraphRAG:
    """
    GraphRAG 混合檢索器 (v5.0 SOTA)。
    使用 LLM 做真實的 NER / Relation Extraction，不再用 if/else 假判斷。
    """

    def __init__(self, engine: Any, graph: PersonalKnowledgeGraph):
        self.engine = engine
        self.graph = graph
        self.mem0 = Mem0Provider() if Mem0Provider else None
        logger.info(f"🧠 GraphRAG 混合聯想引擎初始化完成 (Mem0 Available: {bool(self.mem0)})")

    # ----------------------------------------------------------
    # 知識攝入 (Ingest)
    # ----------------------------------------------------------
    async def ingest_memory(self, session_text: str) -> int:
        """
        從對話文本中自動抽取 RDF 三元組，存入知識圖譜。
        使用 LLM 進行結構化 NER + Relation Extraction。
        """
        logger.info(f"📥 從對話抽取知識: {session_text[:50]}...")

        extraction_prompt = """You are a knowledge graph extraction engine.
Extract ALL factual relationships from the following conversation text.

Rules:
- Extract personal preferences, facts, dates, relationships, opinions
- Output ONLY a JSON array of triples: [["Subject", "Predicate", "Object"]]
- Use lowercase for all entities
- Be specific: "user" not "the person"
- Extract implicit facts too (e.g., "I hate red" → ["user", "dislikes", "red"])

Examples:
- "My wife's birthday is Oct 16" → [["user's wife", "has_birthday", "october 16th"]]
- "I prefer dark mode" → [["user", "prefers", "dark mode"]]
- "Don't use red in the UI" → [["user", "dislikes", "red ui"]]

Text to analyze:
"""

        messages = [
            {"role": "system", "content": extraction_prompt},
            {"role": "user", "content": session_text},
        ]

        try:
            response = await self.engine.gateway.call(
                messages=messages,
                agent_id="default",
                temperature=0.1,
            )
            raw = response["choices"][0]["message"]["content"]
            triplets = self._parse_triplets(raw)

            for s, p, o in triplets:
                self.graph.add_triple(s, p, o, source="graphrag_extraction")

            # 雙寫：同時存入 Mem0 向量記憶 (If available)
            if self.mem0:
                self.mem0.add_memory(session_text)

            logger.info(f"✅ 抽取並存入 {len(triplets)} 條知識三元組")
            return len(triplets)

        except Exception as e:
            logger.error(f"❌ 知識抽取失敗: {e}")
            return 0

    # ----------------------------------------------------------
    # 上下文召回 (Retrieve)
    # ----------------------------------------------------------
    async def retrieve_context(self, query: str) -> str:
        """
        從使用者查詢中抽取相關實體，然後從圖譜中召回 2-hop 子圖作為上下文。
        """
        logger.info(f"🔍 GraphRAG 召回: '{query[:50]}...'")

        # Step 1: 使用 LLM 從查詢中抽取實體
        entities = await self._extract_entities(query)

        if not entities:
            logger.info("ℹ️ 未從查詢中偵測到相關實體")
            return ""

        logger.info(f"🏷️ 偵測到實體: {entities}")

        # Step 2: 從圖譜中召回子圖
        subgraph = self.graph.get_subgraph(entities, max_depth=2)

        if not subgraph:
            logger.info("ℹ️ 圖譜中無相關連結")
            return ""

        # Step 3: 轉為自然語言上下文
        context_lines = ["\n[Personal Knowledge Graph Context]:"]
        for s, p, o in subgraph:
            context_lines.append(f"  - {s} → {p} → {o}")

        graph_str = "\n".join(context_lines)
        
        # Step 4: 合併 Mem0 Vector 記憶 (Hybrid Search)
        if self.mem0:
            mem0_str = self.mem0.search_memory(query)
            if mem0_str:
                graph_str += "\n" + mem0_str

        logger.info(f"💡 召回 {len(subgraph)} 條知識事實 (Hybrid Mode: {bool(self.mem0)})")
        return graph_str

    # ----------------------------------------------------------
    # LLM-based Entity Extraction
    # ----------------------------------------------------------
    async def _extract_entities(self, query: str) -> List[str]:
        """使用 LLM 從查詢中抽取可能的知識圖譜實體。"""
        prompt = """Extract entity names from the following query that might exist in a personal knowledge graph.
Focus on: people, preferences, dates, topics, tools, colors, etc.

Return ONLY a JSON array of lowercase strings. Example: ["user's wife", "dark mode", "python"]
If no entities found, return: []

Query: """

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": query},
        ]

        try:
            response = await self.engine.gateway.call(
                messages=messages,
                agent_id="default",
                temperature=0.1,
            )
            raw = response["choices"][0]["message"]["content"]
            return self._parse_entity_list(raw)
        except Exception as e:
            logger.warning(f"⚠️ 實體抽取失敗，退回關鍵字比對: {e}")
            return self._fallback_entity_extraction(query)

    # ----------------------------------------------------------
    # Fallback: 關鍵字比對 (無 LLM 時)
    # ----------------------------------------------------------
    @staticmethod
    def _fallback_entity_extraction(query: str) -> List[str]:
        """無 LLM 時的簡易實體抽取 (停用詞過濾 + 長度篩選)。"""
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "of", "in", "to",
                      "for", "and", "or", "but", "not", "what", "who", "how", "when",
                      "where", "do", "does", "did", "my", "your", "his", "her", "it",
                      "this", "that", "我", "你", "的", "是", "了", "嗎", "在", "有"}
        words = query.lower().replace("？", "").replace("?", "").split()
        return [w for w in words if w not in stop_words and len(w) > 1]

    # ----------------------------------------------------------
    # JSON parsers
    # ----------------------------------------------------------
    @staticmethod
    def _parse_triplets(raw: str) -> List[List[str]]:
        """解析 LLM 回傳的三元組 JSON 陣列。"""
        text = raw.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [t for t in data if isinstance(t, list) and len(t) == 3]
        except json.JSONDecodeError:
            pass
        return []

    @staticmethod
    def _parse_entity_list(raw: str) -> List[str]:
        """解析 LLM 回傳的實體列表。"""
        text = raw.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [str(e).lower().strip() for e in data if e]
        except json.JSONDecodeError:
            pass
        return []
