import logging
import networkx as nx
import os
import json
from typing import List, Tuple, Dict, Any

logger = logging.getLogger(__name__)

class PersonalKnowledgeGraph:
    """
    基於 NetworkX 的在地化知識圖譜 (Graph Database 概念)。
    負責儲存、讀取與遍歷 RDF (Resource Description Framework) 三元組。
    保存檔案為 JSON 格式 (Node-Link)，輕量快速，無伺服器相依。
    """
    def __init__(self, data_path: str = "data/pkg/graph.json"):
        self.data_path = os.path.join(os.getcwd(), data_path)
        self.graph = nx.DiGraph()
        self._load_graph()
        logger.info(f"🕸️ PersonalKnowledgeGraph 初始化完成，目前包含 {self.graph.number_of_nodes()} 個實體。")

    def _load_graph(self):
        """從本地端讀取圖譜狀態"""
        if os.path.exists(self.data_path):
            try:
                with open(self.data_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.graph = nx.node_link_graph(data)
            except Exception as e:
                logger.error(f"❌ 讀取圖譜失敗: {e}")

    def _save_graph(self):
        """將圖譜狀態存回硬碟"""
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
        try:
            data = nx.node_link_data(self.graph)
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"❌ 儲存圖譜失敗: {e}")

    def add_triple(self, subject: str, predicate: str, obj: str, source: str = "memory"):
        """
        新增三元組 (Subject -> Predicate -> Object)
        例如: ("User", "dislikes", "red UI")
        """
        # 正規化實體名稱
        s = subject.strip().lower()
        o = obj.strip().lower()
        p = predicate.strip().lower()

        # 增加節點
        if not self.graph.has_node(s):
            self.graph.add_node(s, type="entity")
        if not self.graph.has_node(o):
            self.graph.add_node(o, type="entity")

        # 增加邊 (關係)
        # 用 dict 紀錄 source memory id 等 metadata
        self.graph.add_edge(s, o, relation=p, source=source)
        logger.info(f"🔗 圖譜新增關係: [{s}] --({p})--> [{o}]")
        self._save_graph()

    def get_subgraph(self, entities: List[str], max_depth: int = 1) -> List[Tuple[str, str, str]]:
        """
        尋找以指定實體為起點的周遭關係網，作為 GraphRAG 的 Context。
        """
        results = []
        visited = set()
        
        for entity in entities:
            e = entity.strip().lower()
            if not self.graph.has_node(e):
                continue
                
            # 使用 BFS 搜尋 N 階層的鄰居
            edges = nx.bfs_edges(self.graph, e, depth_limit=max_depth)
            for u, v in edges:
                if (u, v) not in visited:
                    visited.add((u, v))
                    rel = self.graph[u][v].get("relation", "related_to")
                    results.append((u, rel, v))
                    
        return results

    def display_stats(self) -> Dict[str, Any]:
        """回傳圖譜大小摘要"""
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges()
        }
