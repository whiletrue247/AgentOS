# AgentOS v5.0: Claude Handoff & Architecture Audit Alignment

Hello Claude!
The user has been working with me (AgentOS Antigravity) to build the foundational framework of **AgentOS v5.0**. We have successfully built the **Object-Oriented interfaces, mocked abstraction layers, and architectural scaffolding**. 

However, the user has very strict **"Hard Tech Stack" requirements** for the final implementation. Currently, the local codebase uses "mocked" or "pure python" placeholders instead of those specific libraries.

Your objective is to read this document, understand what has been built, and help the user **replace our scaffolding with the actual deep-tech implementations** (e.g., `litellm`, `LangGraph`, `Neo4j`, `WASM`).

---

## 🏗️ 1. Hybrid Model Router
**Target Tech Stack:** 自建 `ModelRouter` + `Ollama` + `litellm` (支援 100+ 模型) + NPU 偵測 (`torch.mps` 或 `onnxruntime`)
**Current Local Implementation:**
- 📄 **File:** `self-built inside 04_Engine/router.py` & `04_Engine/gateway.py`
- **What is done:** A basic `SmartRouter` class that switches between local 'ollama' and cloud.
- **Missing / Action Items:** 
  1. We are NOT using `litellm` yet. You need to rewrite `gateway.py` / `router.py` to pipe all proxy calls through the `litellm` package.
  2. NPU detection is currently pure mockup. You need to implement actual hardware detection using `torch.backends.mps.is_available()` or `onnxruntime`.

## 🤖 2. Multi-Agent Orchestration
**Target Tech Stack:** `LangGraph` (圖形化流程) + `CrewAI` (角色扮演) 混合，並且設定 SOUL Orchestrator 需要 Human in the loop。
**Current Local Implementation:**
- 📄 **File:** `05_Orchestrator/sub_agents.py`, `05_Orchestrator/a2a_bus.py`, `05_Orchestrator/task_planner.py`
- **What is done:** A pure Python Event Bus (`a2a_bus.py`) that spawns mock agents based on role prompts (Researcher, Coder, Critic).
- **Missing / Action Items:** 
  1. Rip out the pure python event bus and replace it with a native `LangGraph` StateGraph.
  2. Integrate `CrewAI` definitions for the individual sub-agents.

## 💻 3. Computer Use Runtime
**Target Tech Stack:** Anthropic Computer Use API (2026) + Open Source fallback (`Playwright` + `Vision`). Human preview with 3 choices (Run/Modify/Cancel).
**Current Local Implementation:**
- 📄 **File:** `06_Embodiment/desktop_runtime.py`, `06_Embodiment/browser_cdp.py`, `06_Embodiment/semantic_vision.py`, `04_Engine/zero_trust.py`
- **What is done:** Standard API interfaces for `mouse_click`, `type_text`, and `ZeroTrustInterceptor`. We also built native hooks scaffolding in `09_OS_Integration/os_hook.py`.
- **Missing / Action Items:** 
  1. Actually map the API calls to the real Anthropic Computer Use API payload formatting.
  2. The User-Preview interceptor currently just logs and block. We need an actual GUI/CLI prompt that shows the screenshot and provides exact `[1] Execute [2] Modify [3] Cancel` logic.

## 🧠 4. Personal Knowledge Graph (PKG)
**Target Tech Stack:** `Mem0` + `GraphRAG` + `Neo4j` Community. Auto-decay of unused entities after 7 days.
**Current Local Implementation:**
- 📄 **File:** `07_PKG/knowledge_graph.py`, `07_PKG/graph_rag.py`
- **What is done:** We used `NetworkX` (in-memory/JSON) to build a mock RDF triple store.
- **Missing / Action Items:** 
  1. Replace `NetworkX` with actual `Neo4j` Cypher queries. 
  2. Implement `Mem0` for hybrid vector/graph semantic search.
  3. Implement the `Weight Decay` algorithm (e.g., cronjob that decreases edge weights by a halving factor or linear drop over 7 days).

---

## 📂 Core Reference Files for Claude
Below is a list of the most important files we wrote in this Phase 5/6 sprint. You should read these files to understand the current boundaries:

1. **Orchestrator & DAG:** `05_Orchestrator/a2a_bus.py`, `05_Orchestrator/task_planner.py`
2. **Computer Use & Vision:** `06_Embodiment/desktop_runtime.py`, `06_Embodiment/semantic_vision.py`, `09_OS_Integration/os_hook.py`
3. **Graph & LoRA:** `07_PKG/knowledge_graph.py`, `04_Engine/daily_feedback.py`
4. **Zero Trust & Security:** `04_Engine/zero_trust.py`, `08_Dashboard/audit_trail.py`
5. **Ecosystem & Crypto:** `10_Marketplace/store_manager.py`, `11_Sync_Handoff/handoff_manager.py`

Please assist the user in migrating these conceptual abstractions into the **Hard Tech Stack** targets they've specified!
