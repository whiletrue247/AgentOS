# AgentOS v5.0 — Full SOTA Audit Report
> Audited: 2026-03-03 | Auditor: Claude (Antigravity handoff) | Codebase: 53 files, 6,619 LOC

---

## Executive Summary

AgentOS v5.0 has **solid OOP scaffolding** across 6 development phases. However, **all four target pillars are currently pure-Python mocks** with zero integration of the specified SOTA libraries. For a public SOTA-grade release, significant deepening is required.

| Pillar | Target Stack | Current State | SOTA Gap |
|--------|-------------|---------------|----------|
| Hybrid Router | `litellm` + NPU (`torch`/`onnxruntime`) | Custom `SmartRouter` + JSON lookup | 🔴 Critical |
| Multi-Agent | `LangGraph` + `CrewAI` | Pure Python Event Bus | 🔴 Critical |
| Computer Use | Anthropic API + `Playwright` | Mock `return "base64_dummy"` | 🟡 Medium |
| Personal KG | `Neo4j` + `Mem0` + 7-day decay | `NetworkX` in-memory, no decay | 🔴 Critical |

---

## 🔴 Category A: Critical Gaps (Must fix for SOTA)

### A1. Hybrid Model Router — `04_Engine/router.py` + `gateway.py`
**Current:** Custom `SmartRouter` reads `model_capabilities.json`, does if/else routing.
**Problem:**
- No `litellm` integration → cannot support 100+ models out of box
- No NPU detection → `torch.backends.mps.is_available()` or `onnxruntime.get_available_providers()` is absent
- No cost-based auto-downgrade logic (just complexity-based string matching)
- `gateway.py` manually constructs `httpx` requests per-provider instead of using `litellm.acompletion()`

**Fix Plan:**
1. `pip install litellm` → replace `APIGateway._do_call()` with `litellm.acompletion(model, messages, tools)`
2. Add `04_Engine/npu_detector.py` with `torch`/`onnxruntime` hardware probing
3. Add cost-aware routing: query `litellm.model_cost` to auto-downgrade when budget is low

---

### A2. Multi-Agent Orchestration — `05_Orchestrator/`
**Current:** `a2a_bus.py` = hand-rolled `asyncio.gather()` DAG executor. `sub_agents.py` = static prompt strings.
**Problem:**
- No `LangGraph` StateGraph → no visual graph editor, no conditional edges, no checkpointing
- No `CrewAI` → no role-play delegation, no inter-agent memory sharing
- `task_planner.py` uses mock LLM calls (`# TODO: call Gateway`)
- DAG deadlock detection is naive (just `break`)

**Fix Plan:**
1. `pip install langgraph` → rewrite `a2a_bus.py` as a `StateGraph` with typed state
2. `pip install crewai` → define `Agent()` objects with roles, goals, backstory
3. Wire `TaskPlanner` to actually call the Gateway for LLM-based decomposition
4. Add Human-in-the-loop node in the graph for approval gates

---

### A3. Personal Knowledge Graph — `07_PKG/`
**Current:** `NetworkX` DiGraph stored as JSON. `graph_rag.py` uses mock LLM extraction.
**Problem:**
- No `Neo4j` → cannot scale beyond in-memory, no Cypher queries, no graph visualization
- No `Mem0` → no hybrid vector+graph semantic search
- No weight decay → entities never expire (7-day auto-forget is missing)
- `graph_rag.py` mock extraction uses hardcoded if/else instead of real NER

**Fix Plan:**
1. `pip install neo4j` → replace `nx.DiGraph` with Bolt driver + Cypher queries
2. `pip install mem0ai` → integrate `Memory()` class for vector+graph hybrid
3. Add `07_PKG/decay_scheduler.py` with cron-based edge weight halving (7-day TTL)
4. Replace mock NER with actual LLM structured output extraction

---

## 🟡 Category B: Medium Gaps (Important for quality)

### B1. Computer Use Runtime — `06_Embodiment/`
**Current:** All methods return mock strings like `"base64_encoded_dummy_screenshot_data"`.
**Problem:**
- `desktop_runtime.py` — every method is a no-op with comments like `# pyautogui.click(x, y)`
- `browser_cdp.py` — simulated CDP, no actual Chrome connection
- `semantic_vision.py` — returns hardcoded coordinates `{"x": 960, "y": 540}`
- No Anthropic Computer Use API integration
- Missing "Execute/Modify/Cancel" human preview workflow

**Fix Plan:**
1. Add optional `pyautogui`/`pynput` imports with graceful fallback
2. Integrate `playwright` for real browser automation
3. Add Anthropic `computer_use` beta tool support in Gateway
4. Implement screenshot-based approval flow in `zero_trust.py`

### B2. Zero Trust & Sandbox — Phase 4 (Incomplete)
- `sandbox_firecracker.py` and `wasm_runtime.py` are listed but never created
- `zero_trust.py` only blocks `rm -rf` pattern, not a comprehensive allowlist

### B3. Daily Feedback & LoRA — `04_Engine/daily_feedback.py` + `lora_tuner.py`
- Both use 100% mock data, no actual training pipeline
- `lora_tuner.py` has `# Mock: 不執行真實的微調`

---

## 🟢 Category C: Code Hygiene Issues

### C1. Orphaned Legacy Directories
These directories exist alongside the active modules but appear to be from an older architecture:
- `01_Kernel_Prompt/` (vs active `01_Kernel/`)
- `02_Memory/` (vs active `02_Memory_Context/`)
- `03_Tool_Registry/` (vs active `03_Tool_System/`)
- `04_Sandbox_Execution/` (vs active `04_Engine/`)
- `05_24_7_Engine/` (vs active `05_Orchestrator/`)
- `06_External_Senses/` (vs active `06_Embodiment/`)

**Action:** Audit for any code still referenced, then delete or merge.

### C2. Stale Files
- `fix_quotes.py` — temporary lint fix script committed to repo, should be deleted
- `script.sh` — unknown purpose, 139 bytes

### C3. Missing `__init__.py`
None of the numbered directories have `__init__.py` files, forcing all imports to use `sys.path` hacks or `importlib`.

### C4. Documentation Drift
- `README.md` says "v4.0" but code is v5.0
- `DEV_STATUS.md` tracks Phase 1-5 (original build) but doesn't reflect Phase 1-6 (v5.0 sprint)
- Two separate tracking systems: `DEV_STATUS.md` (original) vs `task_v5.md` (v5.0 sprint, in brain dir)

---

## 📋 Recommended Execution Plan (for Claude or next AI)

### Sprint 1: Foundation Cleanup (Est. 1-2 hours)
- [ ] Delete orphaned legacy directories after confirming no live references
- [ ] Delete `fix_quotes.py`, `script.sh`
- [ ] Add `__init__.py` to all module directories
- [ ] Unify `DEV_STATUS.md` + `task_v5.md` into one source of truth
- [ ] Update `README.md` to v5.0

### Sprint 2: Hybrid Router Deep Integration (Est. 2-3 hours)
- [ ] Install `litellm`, rewrite `gateway.py` to use `litellm.acompletion()`
- [ ] Create `04_Engine/npu_detector.py` with real hardware probing
- [ ] Add cost-aware downgrade logic in `router.py`
- [ ] Write integration tests with mocked `litellm` responses

### Sprint 3: Multi-Agent with LangGraph (Est. 2-3 hours)
- [ ] Install `langgraph`, rewrite `a2a_bus.py` as `StateGraph`
- [ ] Install `crewai`, define agent roles as `CrewAI.Agent()` objects
- [ ] Wire `task_planner.py` to real LLM decomposition
- [ ] Add human-in-the-loop approval node

### Sprint 4: Knowledge Graph with Neo4j (Est. 2-3 hours)
- [ ] Install `neo4j` driver, replace `NetworkX` with Cypher
- [ ] Install `mem0ai`, integrate hybrid search
- [ ] Implement 7-day decay scheduler
- [ ] Write tests verifying entity expiration

### Sprint 5: Computer Use & Polish (Est. 2-3 hours)
- [ ] Add real `pyautogui`/`playwright` implementations
- [ ] Integrate Anthropic Computer Use API format
- [ ] Build Execute/Modify/Cancel approval workflow
- [ ] Final `pyflakes` + `pytest` full sweep
- [ ] Push to GitHub with clean CI

---

## File Reference Map

| Module | Key Files | LOC | Status |
|--------|-----------|-----|--------|
| Kernel | `01_Kernel/kernel.py`, `soul_generator.py` | ~130 | ✅ Functional |
| Memory | `02_Memory_Context/memory_manager.py` | ~180 | ✅ Functional |
| Tools | `03_Tool_System/catalog.py`, `sandbox_subprocess.py` | ~400 | ✅ Functional |
| Engine | `04_Engine/engine.py`, `gateway.py`, `router.py` | ~680 | ⚠️ Needs litellm |
| Orchestrator | `05_Orchestrator/a2a_bus.py`, `task_planner.py` | ~280 | ⚠️ Needs LangGraph |
| Embodiment | `06_Embodiment/desktop_runtime.py`, `browser_cdp.py` | ~180 | ⚠️ All mocked |
| PKG | `07_PKG/knowledge_graph.py`, `graph_rag.py` | ~160 | ⚠️ Needs Neo4j |
| Dashboard | `08_Dashboard/audit_trail.py`, `cli_dashboard.py` | ~130 | ✅ Functional |
| OS Hooks | `09_OS_Integration/os_hook.py` | ~80 | ⚠️ Mocked |
| Marketplace | `10_Marketplace/store_manager.py` | ~95 | ⚠️ Mocked |
| Sync | `11_Sync_Handoff/handoff_manager.py` | ~65 | ✅ Functional (base64 serialization works) |
