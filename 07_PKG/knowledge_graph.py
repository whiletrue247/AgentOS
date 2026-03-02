"""
07_PKG — Personal Knowledge Graph (v5.0 SOTA — Neo4j + NetworkX Fallback)
===========================================================================
儲存使用者的個人知識關係 (RDF 三元組)。
  - Neo4j 模式：使用 Bolt Driver + Cypher 查詢 (量產級)
  - NetworkX 模式：本地 JSON 圖 (無伺服器部署模式)

支援 GraphRAG 子圖檢索與 7 天自動衰減 (見 decay_scheduler.py)。
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 嘗試載入 Neo4j
try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False

# NetworkX 作為 fallback
try:
    import networkx as nx
    NX_AVAILABLE = True
except ImportError:
    NX_AVAILABLE = False


class PersonalKnowledgeGraph:
    """
    個人知識圖譜 (v5.0 SOTA)。
    優先使用 Neo4j (Bolt)；未安裝或未配置時退回 NetworkX (JSON)。
    每個邊 (關係) 帶有 weight 和 last_accessed 時間戳，供衰減排程器使用。
    """

    def __init__(
        self,
        neo4j_uri: Optional[str] = None,
        neo4j_user: str = "neo4j",
        neo4j_password: str = "",
        data_path: str = "data/pkg/graph.json",
    ):
        self.mode: str = "none"
        self._driver = None
        self._nx_graph = None
        self._data_path = os.path.join(os.getcwd(), data_path)

        # 嘗試 Neo4j
        if NEO4J_AVAILABLE and neo4j_uri:
            try:
                self._driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
                self._driver.verify_connectivity()
                self.mode = "neo4j"
                logger.info(f"🕸️ PKG: Connected to Neo4j at {neo4j_uri}")
            except Exception as e:
                logger.warning(f"⚠️ Neo4j connection failed ({e}), falling back to NetworkX")
                self._driver = None

        # Fallback: NetworkX
        if self.mode == "none" and NX_AVAILABLE:
            self._nx_graph = nx.DiGraph()
            self._load_nx_graph()
            self.mode = "networkx"
            logger.info(f"🕸️ PKG: Using NetworkX (local JSON), {self._nx_graph.number_of_nodes()} entities loaded")

        if self.mode == "none":
            logger.error("❌ PKG: Neither Neo4j nor NetworkX available!")

    def close(self):
        if self._driver:
            self._driver.close()

    # ========================================================
    # ADD TRIPLE
    # ========================================================
    def add_triple(self, subject: str, predicate: str, obj: str, source: str = "memory"):
        """新增三元組 (Subject → Predicate → Object)，附帶 weight 與時間戳。"""
        s, p, o = subject.strip().lower(), predicate.strip().lower(), obj.strip().lower()
        now = time.time()

        if self.mode == "neo4j":
            self._neo4j_add(s, p, o, source, now)
        elif self.mode == "networkx":
            self._nx_add(s, p, o, source, now)

        logger.info(f"🔗 圖譜新增: [{s}] --({p})--> [{o}]")

    def _neo4j_add(self, s: str, p: str, o: str, source: str, now: float):
        with self._driver.session() as session:
            session.run(
                """
                MERGE (a:Entity {name: $s})
                MERGE (b:Entity {name: $o})
                MERGE (a)-[r:RELATION {type: $p}]->(b)
                SET r.source = $source, r.weight = coalesce(r.weight, 1.0),
                    r.last_accessed = $now, r.created_at = coalesce(r.created_at, $now)
                """,
                s=s, o=o, p=p, source=source, now=now,
            )

    def _nx_add(self, s: str, p: str, o: str, source: str, now: float):
        if not self._nx_graph.has_node(s):
            self._nx_graph.add_node(s, type="entity")
        if not self._nx_graph.has_node(o):
            self._nx_graph.add_node(o, type="entity")

        if self._nx_graph.has_edge(s, o):
            self._nx_graph[s][o]["weight"] = self._nx_graph[s][o].get("weight", 1.0) + 0.1
            self._nx_graph[s][o]["last_accessed"] = now
        else:
            self._nx_graph.add_edge(s, o, relation=p, source=source, weight=1.0,
                                     last_accessed=now, created_at=now)
        self._save_nx_graph()

    # ========================================================
    # GET SUBGRAPH (for GraphRAG context)
    # ========================================================
    def get_subgraph(self, entities: List[str], max_depth: int = 1) -> List[Tuple[str, str, str]]:
        """檢索以指定實體為中心的周遭關係，供 GraphRAG 注入上下文。"""
        if self.mode == "neo4j":
            return self._neo4j_subgraph(entities, max_depth)
        elif self.mode == "networkx":
            return self._nx_subgraph(entities, max_depth)
        return []

    def _neo4j_subgraph(self, entities: List[str], max_depth: int) -> List[Tuple[str, str, str]]:
        results = []
        with self._driver.session() as session:
            for entity in entities:
                e = entity.strip().lower()
                records = session.run(
                    f"""
                    MATCH (a:Entity {{name: $name}})-[r:RELATION*1..{max_depth}]->(b:Entity)
                    RETURN a.name AS s, r[-1].type AS p, b.name AS o
                    LIMIT 50
                    """,
                    name=e,
                )
                for rec in records:
                    results.append((rec["s"], rec["p"], rec["o"]))
                # 更新 last_accessed
                session.run(
                    "MATCH (a:Entity {name: $name})-[r:RELATION]->() SET r.last_accessed = $now",
                    name=e, now=time.time(),
                )
        return results

    def _nx_subgraph(self, entities: List[str], max_depth: int) -> List[Tuple[str, str, str]]:
        results = []
        visited = set()
        for entity in entities:
            e = entity.strip().lower()
            if not self._nx_graph.has_node(e):
                continue
            edges = nx.bfs_edges(self._nx_graph, e, depth_limit=max_depth)
            for u, v in edges:
                if (u, v) not in visited:
                    visited.add((u, v))
                    rel = self._nx_graph[u][v].get("relation", "related_to")
                    results.append((u, rel, v))
                    # 更新 last_accessed
                    self._nx_graph[u][v]["last_accessed"] = time.time()
        self._save_nx_graph()
        return results

    # ========================================================
    # DECAY (7-day weight halving)
    # ========================================================
    def apply_decay(self, half_life_days: float = 7.0, min_weight: float = 0.05) -> int:
        """
        對所有邊執行時間衰減。
        公式: new_weight = weight * 0.5^(days_since_access / half_life_days)
        低於 min_weight 的邊會被刪除。
        回傳: 被刪除的邊數量。
        """
        if self.mode == "neo4j":
            return self._neo4j_decay(half_life_days, min_weight)
        elif self.mode == "networkx":
            return self._nx_decay(half_life_days, min_weight)
        return 0

    def _neo4j_decay(self, half_life_days: float, min_weight: float) -> int:
        now = time.time()
        with self._driver.session() as session:
            # 批量更新 weight
            session.run(
                """
                MATCH ()-[r:RELATION]->()
                WITH r, duration.inSeconds(datetime({epochSeconds: toInteger(r.last_accessed)}),
                     datetime({epochSeconds: toInteger($now)})).seconds / 86400.0 AS days
                SET r.weight = r.weight * (0.5 ^ (days / $half_life))
                """,
                now=now, half_life=half_life_days,
            )
            # 刪除低權重邊
            result = session.run(
                "MATCH ()-[r:RELATION]->() WHERE r.weight < $min DELETE r RETURN count(r) AS cnt",
                min=min_weight,
            )
            deleted = result.single()["cnt"]

            # 清理孤立節點
            session.run("MATCH (n:Entity) WHERE NOT (n)--() DELETE n")

        logger.info(f"🧹 Neo4j decay: deleted {deleted} weak edges")
        return deleted

    def _nx_decay(self, half_life_days: float, min_weight: float) -> int:
        now = time.time()
        to_remove = []
        for u, v, data in self._nx_graph.edges(data=True):
            last = data.get("last_accessed", now)
            days = (now - last) / 86400
            new_weight = data.get("weight", 1.0) * (0.5 ** (days / half_life_days))
            if new_weight < min_weight:
                to_remove.append((u, v))
            else:
                self._nx_graph[u][v]["weight"] = new_weight

        for u, v in to_remove:
            self._nx_graph.remove_edge(u, v)

        # 清理孤立節點
        isolates = list(nx.isolates(self._nx_graph))
        self._nx_graph.remove_nodes_from(isolates)

        self._save_nx_graph()
        logger.info(f"🧹 NetworkX decay: removed {len(to_remove)} edges, {len(isolates)} orphans")
        return len(to_remove)

    # ========================================================
    # STATS
    # ========================================================
    def display_stats(self) -> Dict[str, Any]:
        if self.mode == "neo4j":
            with self._driver.session() as session:
                nodes = session.run("MATCH (n:Entity) RETURN count(n) AS c").single()["c"]
                edges = session.run("MATCH ()-[r:RELATION]->() RETURN count(r) AS c").single()["c"]
            return {"mode": "neo4j", "nodes": nodes, "edges": edges}
        elif self.mode == "networkx":
            return {
                "mode": "networkx",
                "nodes": self._nx_graph.number_of_nodes(),
                "edges": self._nx_graph.number_of_edges(),
            }
        return {"mode": "none", "nodes": 0, "edges": 0}

    # ========================================================
    # NetworkX persistence
    # ========================================================
    def _load_nx_graph(self):
        if os.path.exists(self._data_path):
            try:
                with open(self._data_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._nx_graph = nx.node_link_graph(data)
            except Exception as e:
                logger.error(f"❌ 載入圖譜失敗: {e}")

    def _save_nx_graph(self):
        os.makedirs(os.path.dirname(self._data_path), exist_ok=True)
        try:
            data = nx.node_link_data(self._nx_graph)
            with open(self._data_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"❌ 儲存圖譜失敗: {e}")
