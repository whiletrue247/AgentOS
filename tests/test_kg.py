"""
tests/test_kg.py
================
Unit tests for knowledge graph fallback (NetworkX mode) and time-based decay logic.
"""

import sys
import os
import time
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import importlib.util

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

kg_mod = load_module("knowledge_graph", os.path.abspath("07_PKG/knowledge_graph.py"))
PersonalKnowledgeGraph = kg_mod.PersonalKnowledgeGraph

# Test constants
TEST_GRAPH_PATH = "tests/test_graph.json"


@pytest.fixture
def nx_graph():
    """建立乾淨的 NetworkX 圖譜供測試使用"""
    if os.path.exists(TEST_GRAPH_PATH):
        os.remove(TEST_GRAPH_PATH)
        
    kg = PersonalKnowledgeGraph(neo4j_uri=None, data_path=TEST_GRAPH_PATH)
    assert kg.mode == "networkx"
    yield kg
    
    if os.path.exists(TEST_GRAPH_PATH):
        os.remove(TEST_GRAPH_PATH)


def test_add_triple(nx_graph):
    """新增三元組並驗證 get_subgraph 回傳"""
    nx_graph.add_triple("Alice", "knows", "Bob")
    nx_graph.add_triple("Bob", "likes", "AI")
    
    # 搜尋中心實體 "Alice"
    subgraph = nx_graph.get_subgraph(["alice"], max_depth=2)
    assert len(subgraph) >= 1
    
    edges = [(s, p, o) for s, p, o in subgraph]
    assert ("alice", "knows", "bob") in edges
    assert ("bob", "likes", "ai") in edges


def test_stats(nx_graph):
    """驗證 display_stats 回傳正確數字"""
    nx_graph.add_triple("Dog", "is_a", "Animal")
    
    stats = nx_graph.display_stats()
    assert stats["mode"] == "networkx"
    assert stats["nodes"] == 2
    assert stats["edges"] == 1


def test_decay(nx_graph):
    """手動修改 last_accessed 到 14 天前，執行 decay，驗證被刪除"""
    nx_graph.add_triple("Old_Memory", "forgotten", "True")
    
    # 強制修改 NetworkX 內部邊的 last_accessed
    # days = 14 => 2半衰期 => 0.25 weight => 小於 0.05 是因為 weight 是 0.1 開始?
    # original add_triple adds weight=1.0 initially. Wait, looking at the code, edge add gives weight 1.0!
    # days = 14 => weight=1.0 * (0.5 ^ 2) = 0.25 (which is > 0.05).
    # To delete it, we either need it to be 40 days old, or change min_weight.
    # We will pass min_weight=0.3 to apply_decay to assert deletion.
    
    now = time.time()
    nx_graph._nx_graph["old_memory"]["true"]["last_accessed"] = now - (14 * 86400)
    
    deleted_edges = nx_graph.apply_decay(half_life_days=7.0, min_weight=0.3)
    
    # 邊應該被刪除，且因為變成孤立節點，節點也會被清空
    assert deleted_edges == 1
    stats = nx_graph.display_stats()
    assert stats["edges"] == 0
    assert stats["nodes"] == 0


def test_decay_keeps_recent(nx_graph):
    """驗證最近存取的實體不被刪除"""
    nx_graph.add_triple("New_Memory", "remembers", "Everything")
    
    now = time.time()
    # 1 天前
    nx_graph._nx_graph["new_memory"]["everything"]["last_accessed"] = now - 86400
    
    deleted_edges = nx_graph.apply_decay(half_life_days=7.0, min_weight=0.05)
    
    assert deleted_edges == 0
    stats = nx_graph.display_stats()
    assert stats["edges"] == 1
    assert stats["nodes"] == 2
    
    # 權重衰減一點點
    new_w = nx_graph._nx_graph["new_memory"]["everything"]["weight"]
    assert new_w < 1.0
    assert new_w > 0.8
