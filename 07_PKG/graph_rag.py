import logging
import asyncio
from typing import Any

from knowledge_graph import PersonalKnowledgeGraph

logger = logging.getLogger(__name__)

class GraphRAG:
    """
    GraphRAG 混合檢索器。
    它結合了向量搜尋的語意相似度，以及 NetworkX 知識圖譜的確切關係連結。
    能自動將使用者的隱性記憶 (如老婆生日、討厭某個顏色) 抽成 RDF 並在未來查詢時附上。
    """
    def __init__(self, engine: Any, graph: PersonalKnowledgeGraph):
        self.engine = engine
        self.graph = graph
        logger.info("🧠 GraphRAG 混合聯想引擎初始化完成")

    async def ingest_memory(self, session_text: str):
        """
        每段對話結束，或背景排程 (LoRA_Tuner 概念)，交由 LLM 解析關係並存入 Graph。
        """
        logger.info(f"📥 從對話抽取知識實體: {session_text[:30]}...")
        
        # 實戰中這裡會呼叫 Gateway 進行結構化擷取
        _ = f"""
        Extract entities and relationships from the following text.
        Output format should be a JSON array of arrays: [["Subject", "Predicate", "Object"]].
        Text: {session_text}
        """
        
        # 這裡用 MOCK LLM response 展示架構
        await asyncio.sleep(0.5)
        
        # 假設 LLM 抽出了以下關聯
        mock_triplets = []
        if "老婆生日" in session_text or "wife's birthday" in session_text.lower():
            mock_triplets.append(["user's wife", "has_birthday", "October 16th"])
        if ("紅色" in session_text and "討厭" in session_text) or ("red" in session_text.lower() and "hate" in session_text.lower()):
            mock_triplets.append(["user", "dislikes", "color red"])
            mock_triplets.append(["color red", "triggers", "user annoyance"])
            
        for s, p, o in mock_triplets:
            self.graph.add_triple(s, p, o, source="conversation_extraction")
            
        return len(mock_triplets)

    async def retrieve_context(self, query: str) -> str:
        """
        當 User 發問時，先從 Query 中抽出 Entities，然後進 Graph 抓出 2 Hop Subgraph
        """
        logger.info(f"🔍 GraphRAG 關聯檢索: '{query}'")
        
        # 實測中：呼叫 NER 或簡單比對從 query 抓取名詞
        # 這裡簡化為假定
        target_entities = []
        if "老婆" in query or "wife" in query:
            target_entities.append("user's wife")
        if "顏色" in query or "color" in query or "紅色" in query:
            target_entities.append("user")
            target_entities.append("color red")
            
        # 從 Graph 撈取關聯脈絡
        subgraph = self.graph.get_subgraph(target_entities, max_depth=2)
        
        if not subgraph:
            return ""
            
        # 將 RDF 三元組轉回自然語言 Prompt Context
        context_lines = ["\n[Personal Knowledge Graph Context]:"]
        for s, p, o in subgraph:
            context_lines.append(f" - Fact: [{s}] {p} [{o}]")
            
        graph_str = "\n".join(context_lines)
        logger.info(f"💡 GraphRAG 成功召回 {len(subgraph)} 條核心事實")
        return graph_str
