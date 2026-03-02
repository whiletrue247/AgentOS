import asyncio
import logging
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../07_PKG'))

from knowledge_graph import PersonalKnowledgeGraph
from graph_rag import GraphRAG

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

async def run_pkg_test():
    logger.info("============================================================")
    logger.info("🧠 開始 Personal Knowledge Graph (PKG) 基礎模組測試")
    logger.info("============================================================")
    
    # 建立暫存測試檔案
    temp_db_path = "data/test_pkg_graph.json"
    if os.path.exists(temp_db_path):
        os.remove(temp_db_path)
        
    try:
        # 1. 啟動圖譜
        pkg = PersonalKnowledgeGraph(data_path=temp_db_path)
        
        # 模擬 Gateway Engine
        class MockEngine:
            pass
            
        rag = GraphRAG(engine=MockEngine(), graph=pkg)
        
        # 2. 測試 Ingest Memory (抽取三元組)
        session_text = "I just wanted to remind you that my wife's birthday is coming up on October 16th, and please remember I really hate the color red on any UI designs."
        logger.info("\n--- 測試 1: 記憶抽取 (Ingest Memory) ---")
        await rag.ingest_memory(session_text)
        
        stats = pkg.display_stats()
        logger.info(f"📊 圖譜大小: {stats}")
        assert stats["nodes"] > 0, "圖譜節點不應為 0"
        
        # 3. 測試 GraphRAG Context (檢索)
        logger.info("\n--- 測試 2: GraphRAG 關聯檢索 ---")
        query1 = "What should I buy for my wife's birthday?"
        context1 = await rag.retrieve_context(query1)
        logger.info(context1)
        assert "october 16th" in context1.lower(), "沒有順利查到老婆生日"
        
        query2 = "Should I use the color red for the background?"
        context2 = await rag.retrieve_context(query2)
        logger.info(context2)
        assert "dislikes" in context2 or "triggers" in context2, "沒有順利查到討厭紅色"

        logger.info("\n✅ PKG / GraphRAG 模組測試全部通過！")

    except Exception as e:
        logger.error(f"❌ PKG 測試失敗: {e}")
    finally:
        # 清理暫存檔
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)

if __name__ == "__main__":
    asyncio.run(run_pkg_test())
