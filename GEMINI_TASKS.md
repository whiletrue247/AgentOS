# AgentOS v5.0 — Gemini 任務分解清單

> **規則：**
> 1. 每個任務完成後立即 `git add -A && git commit -m "對應的 commit message"`
> 2. 完成所有任務後，寫一份 `GEMINI_REPORT.md` 詳列每個任務的改動、新增檔案、行數
> 3. 每次 commit 前必須確認 `pyflakes .` 零警告 + `pytest tests/ -v` 全通過
> 4. 代碼禁止使用 `mock`/`sleep()` 假裝實作，必須有真實邏輯或 graceful fallback
> 5. 所有 public class 和 method 必須有 type hints + docstring

---

## Phase A: 容器化與安全強化 (Containerization & Security)

### Task A-1: 硬化 Dockerfile
- **檔案**: `Dockerfile`
- **要求**:
  - 使用 `python:3.12-slim` 作為 base image
  - Multi-stage build: builder stage 安裝依賴 → runtime stage 只複製必要檔案
  - 建立非 root 使用者 `agentos` 執行
  - `COPY requirements.txt` 先裝依賴 (利用 Docker cache)
  - 設定 `HEALTHCHECK`
  - 最終 image 不包含 `.git`, `tests/`, `*.md` (已有 `.dockerignore`)
- **commit**: `🐳 feat(docker): hardened multi-stage Dockerfile with non-root user`

### Task A-2: docker-compose.yml (含 Neo4j + 可選 gVisor)
- **檔案**: `docker-compose.yml`
- **要求**:
  - `agentos` service: 掛載 `config.yaml` + `data/` volume
  - `neo4j` service: 使用 `neo4j:5-community`, 開放 7687 (Bolt) + 7474 (Browser)
  - `sandbox` service (可選): 使用 `runsc` (gVisor) runtime, `runtime: runsc`
  - 網路隔離: `agentos` 與 `neo4j` 同網路, `sandbox` 獨立網路
  - 環境變數: `NEO4J_URI=bolt://neo4j:7687`
- **commit**: `🐳 feat(compose): Neo4j + gVisor sandbox orchestration`

### Task A-3: config.yaml 加密支援
- **檔案**: `config_schema.py` (修改), `utils/secret_manager.py` (新增)
- **要求**:
  - 新增 `utils/secret_manager.py`：
    - `encrypt_value(plaintext, password) -> str`: 使用 `cryptography.fernet` 加密
    - `decrypt_value(ciphertext, password) -> str`: 解密
    - `is_encrypted(value) -> bool`: 檢查是否以 `ENC[` 開頭
  - 修改 `config_schema.py` 的 `load_config()`:
    - 如果 `provider.api_key` 以 `ENC[` 開頭，自動呼叫 `decrypt_value()`
    - 密碼從 `AGENTOS_MASTER_KEY` 環境變數讀取
  - `onboarding.py`: 新增選項讓使用者選擇是否加密存儲 API Key
- **commit**: `🔐 feat(security): Fernet-encrypted API key storage in config.yaml`

### Task A-4: 完整的 Audit Trail Logger
- **檔案**: `04_Engine/audit_trail.py` (新增)
- **要求**:
  - `class AuditTrail`:
    - `log_action(agent_id, action_type, payload, result, risk_level)`: 寫入 SQLite
    - `get_history(agent_id, limit) -> List[AuditEntry]`: 查詢歷史
    - `export_report(date_range) -> str`: 匯出 Markdown 報告
  - 每筆記錄包含: `timestamp, agent_id, action_type, payload_hash, result_status, risk_level, execution_time_ms`
  - 整合進 `sandbox_subprocess.py`: 每次執行前後寫入 audit log
  - 整合進 `zero_trust.py`: 每次攔截寫入 audit log
- **commit**: `📝 feat(audit): SQLite-backed audit trail with full action logging`

---

## Phase B: Marketplace & Token 經濟 (已有骨架，需升級)

### Task B-1: Tool Store — 真實的工具安裝流程
- **檔案**: `10_Marketplace/marketplace.py` (修改)
- **要求**:
  - `install_tool(tool_id)`:
    - 從 `tool_registry.json` (本地) 或 `TOOL_STORE_URL` (遠端) 下載工具定義
    - 驗證 JSON Schema 格式
    - 寫入 `03_Tool_System/catalog.json`
    - 不使用 `exec_module`，改用 JSON Schema 定義 + sandbox 執行
  - `uninstall_tool(tool_id)`: 從 catalog 移除
  - `list_available_tools() -> List[ToolInfo]`: 列出所有可用工具
  - `rate_tool(tool_id, score, review)`: 評分
- **commit**: `🏪 feat(marketplace): real tool install/uninstall/rate flow`

### Task B-2: Soul Gallery — 靈魂分享機制
- **檔案**: `10_Marketplace/soul_gallery.py` (新增)
- **要求**:
  - `class SoulGallery`:
    - `publish_soul(soul_path, metadata) -> str`: 打包 SOUL.md + metadata → `.soul.zip`
    - `import_soul(soul_zip_path) -> str`: 解壓並載入到 `01_Kernel/`
    - `list_gallery() -> List[SoulInfo]`: 列出已安裝靈魂
    - `validate_soul(soul_content) -> Tuple[bool, List[str]]`: 驗證 SOUL.md 格式
  - 每個 Soul 包含: `name, author, version, description, personality_tags, rules_hash`
- **commit**: `🎭 feat(marketplace): Soul Gallery with publish/import/validate`

---

## Phase C: Swarm Orchestration (多 Agent 群體智慧)

### Task C-1: Agent Registry
- **檔案**: `05_Orchestrator/agent_registry.py` (新增)
- **要求**:
  - `class AgentRegistry`:
    - `register(agent_id, capabilities, model_preference) -> AgentProfile`
    - `unregister(agent_id)`
    - `find_agents(capability_filter) -> List[AgentProfile]`: 按能力搜尋
    - `get_status(agent_id) -> AgentStatus`: idle/busy/error
  - `AgentProfile` dataclass: `id, name, capabilities: List[str], model: str, status, created_at`
  - 使用 SQLite 持久化
- **commit**: `🐝 feat(swarm): agent registry with capability-based discovery`

### Task C-2: Swarm Coordinator (多 Agent 協同)
- **檔案**: `05_Orchestrator/swarm_coordinator.py` (新增)
- **要求**:
  - `class SwarmCoordinator`:
    - `form_team(objective, team_size) -> List[AgentProfile]`: 根據目標自動從 registry 挑選 agent
    - `broadcast(message, team) -> List[str]`: 廣播訊息給團隊
    - `collect_votes(question, team) -> Dict[str, str]`: 收集多 agent 意見 (如 code review)
    - `consensus(votes) -> str`: 多數決
  - 使用 `A2ABus.dispatch_task()` 底層派發
- **commit**: `🐝 feat(swarm): multi-agent team formation + consensus voting`

---

## Phase D: 跨裝置同步強化

### Task D-1: Sync Protocol (WebSocket)
- **檔案**: `11_Sync_Handoff/sync_server.py` (新增)
- **要求**:
  - `class SyncServer`:
    - 使用 `websockets` 或 `aiohttp.web.WebSocketServer`
    - `start(host, port)`: 啟動 WebSocket 伺服器
    - `broadcast_state(state_dict)`: 推送狀態給所有連線裝置
    - `on_handoff_request(from_device, to_device, context)`: 處理接力請求
  - `class SyncClient`:
    - `connect(server_url)`: 連線至主機
    - `send_handoff(context)`: 發送接力請求
    - `on_state_update(callback)`: 註冊狀態更新回調
- **commit**: `🔄 feat(sync): WebSocket-based cross-device sync protocol`

### Task D-2: Context Serializer
- **檔案**: `11_Sync_Handoff/context_serializer.py` (新增)
- **要求**:
  - `class ContextSerializer`:
    - `serialize(engine_state, memory_snapshot, kg_subgraph) -> bytes`: 壓縮序列化
    - `deserialize(data: bytes) -> HandoffContext`: 解壓還原
    - `diff(old_state, new_state) -> bytes`: 差異序列化 (減少傳輸量)
  - 使用 `msgpack` + `zlib` 壓縮
  - 包含 checksum 驗證
- **commit**: `🔄 feat(sync): msgpack + zlib context serializer with checksum`

---

## Phase E: 可觀測性 Dashboard 2.0

### Task E-1: 豐富 CLI Dashboard 資訊
- **檔案**: `08_Dashboard/dashboard.py` (修改)
- **要求**:
  - 在現有 Rich 面板上新增:
    - **Audit Trail 面板**: 顯示最近 10 筆操作記錄 (from Task A-4)
    - **KG Stats 面板**: 顯示節點/邊數、最近新增的 triple
    - **Router 面板**: 顯示當前模型、NPU 狀態、session cost
    - **Agent Status 面板**: 顯示 registry 中所有 agent 的狀態
  - 使用 `rich.live.Live` 實現即時更新
- **commit**: `📊 feat(dashboard): audit trail + KG + router + agent panels`

### Task E-2: 模擬未來 10 步 CLI 命令
- **檔案**: `08_Dashboard/cli_commands.py` (新增)
- **要求**:
  - 新增 CLI 命令 `agentos simulate <objective>`:
    - 呼叫 `04_Engine/simulator.py` 的 `simulate_n_steps()`
    - 用 Rich table 顯示每步的 thought/action/risk
    - 最後顯示 summary (total tokens, high risk count)
    - 如果有 high risk，用紅色標記並要求確認
  - 新增 CLI 命令 `agentos audit [--days=7]`:
    - 呼叫 `04_Engine/audit_trail.py` 的 `export_report()`
    - 輸出 Markdown 格式報告
- **commit**: `📊 feat(cli): simulate + audit commands with Rich output`

---

## Phase F: 測試覆蓋補強

### Task F-1: Core Module Unit Tests
- **檔案**: `tests/test_core.py` (新增)
- **要求**:
  - `test_npu_detector()`: 驗證 HardwareProfile 回傳 + recommended_backend 有值
  - `test_router_offline_mode()`: 設定 offline → 確認只路由到本地 provider
  - `test_router_complexity()`: 測試 basic/coding/complex 判定邏輯
  - `test_zero_trust_block()`: 測試 `rm -rf /` 被攔截
  - `test_zero_trust_allow()`: 測試正常指令通過
  - `test_cost_guard()`: 測試預算超支時 get_cheaper_alternative 回傳值
- **commit**: `🧪 test: core module unit tests (router, npu, zero_trust, cost)`

### Task F-2: KG + Decay Tests
- **檔案**: `tests/test_kg.py` (新增)
- **要求**:
  - `test_add_triple()`: 新增三元組並驗證 get_subgraph 回傳
  - `test_decay()`: 手動修改 last_accessed 到 14 天前，執行 decay，驗證被刪除
  - `test_decay_keeps_recent()`: 驗證最近存取的實體不被刪除
  - `test_stats()`: 驗證 display_stats 回傳正確數字
  - 全部使用 NetworkX fallback (不需要 Neo4j server)
- **commit**: `🧪 test: knowledge graph + decay scheduler tests`

### Task F-3: Sandbox Security Tests
- **檔案**: `tests/test_security.py` (新增)
- **要求**:
  - `test_static_block()`: 驗證 `rm -rf /` 直接被靜態攔截
  - `test_env_stripping()`: 驗證 `_build_secure_env()` 移除了 OPENAI_API_KEY
  - `test_path_sanitization()`: 驗證 PATH 中 `/sbin` 被移除
  - `test_timeout_kills_process()`: 啟動 `sleep 999`，設 timeout=2s，驗證被 kill
  - `test_network_deny()`: 驗證 `network_allowed=False` 時設定了 proxy 環境變數
- **commit**: `🧪 test: sandbox security hardening verification`

---

## Phase G: 最終收尾

### Task G-1: 更新 README.md
- **檔案**: `README.md`
- **要求**:
  - 新增 badges: CI status, License, Python version
  - 更新安裝指南: `pip install -e ".[all]"` 或 `docker-compose up`
  - 新增 Quick Start 區塊
  - 新增 Architecture Diagram (Mermaid)
  - 更新模組列表反映最新狀態 (11 個模組)
- **commit**: `📖 docs: comprehensive README with badges, install, architecture`

### Task G-2: 撰寫 GEMINI_REPORT.md
- **檔案**: `GEMINI_REPORT.md`
- **要求**: 詳列每個 Task 的:
  - 改動/新增的檔案
  - 行數統計
  - 使用的函式庫/技術
  - 已知限制或 TODO
  - 對應的 commit hash

---

---

## Phase H: 四大支柱補完 (Core Pillar Gap Fill)

> ⚠️ **背景**: 以下 4 項原始需求中，litellm、NPU 偵測、LangGraph、Neo4j+7天衰減 已由 Claude 完成。
> 以下 3 個真正的缺口需要 Gemini 補全。

### Task H-1: CrewAI 角色定義整合
- **檔案**: `05_Orchestrator/crewai_roles.py` (新增), `05_Orchestrator/a2a_bus.py` (修改)
- **背景**: 目前 `a2a_bus.py` 已使用 LangGraph StateGraph，但 CrewAI 的角色扮演機制尚未整合
- **要求**:
  - 新增 `crewai_roles.py`:
    - `class CrewAIRoleAdapter`:
      - `define_crew(objective, roles: List[str]) -> Crew`: 用 CrewAI API 定義團隊
      - `_build_agent(role, goal, backstory) -> crewai.Agent`: 建立角色
      - `_build_task(description, agent, expected_output) -> crewai.Task`: 建立任務
    - 預設角色: `orchestrator`（永遠先問 Human 確認大計畫）, `researcher`, `coder`, `writer`, `critic`
    - 每個角色的 backstory 必須引用 SOUL.md 的人格設定
  - 修改 `a2a_bus.py`:
    - 新增 `run_dag_crewai()` 方法
    - `run_dag()` 入口邏輯: 先嘗試 LangGraph → 退回 CrewAI → 最終 asyncio
  - 當 `crewai` 未安裝時 graceful fallback
- **commit**: `🎭 feat(orchestration): CrewAI role-playing agent integration with LangGraph fallback chain`

### Task H-2: Human Preview UI (執行/修改/取消 三選一)
- **檔案**: `06_Embodiment/human_preview.py` (新增), `08_Dashboard/dashboard.py` (修改)
- **背景**: Computer Use Runtime 已有真實的 pyautogui/Playwright，但操作前的截圖預覽 + 人類確認還沒做
- **要求**:
  - 新增 `human_preview.py`:
    - `class HumanPreviewGate`:
      - `request_approval(action_description, screenshot_b64, risk_level) -> Literal["execute", "modify", "cancel"]`:
        - CLI 模式: 用 `rich.prompt.Prompt` 顯示截圖資訊 + 三選一
        - Telegram 模式: 用 inline keyboard 三個按鈕 (如果 bot 可用)
        - Auto-approve 模式: `risk_level == "low"` 時自動通過
      - `preview_and_execute(desktop_runtime, action_type, action_args) -> ToolCallResult`:
        - Step 1: 截圖 → `take_screenshot()`
        - Step 2: 描述動作 → 呼叫 `request_approval()`
        - Step 3: 根據回覆 → 執行/要求修改/取消
  - 修改 `08_Dashboard/dashboard.py`:
    - 新增 preview 面板: 顯示最近一次人類確認的結果
  - 在 `06_Embodiment/desktop_runtime.py` 的 `click()` 和 `type_text()` 中:
    - 新增可選參數 `require_approval: bool = False`
    - 為 True 時先過 `HumanPreviewGate`
- **commit**: `👤 feat(computer-use): human preview gate — screenshot + Run/Modify/Cancel before execution`

### Task H-3: Mem0 整合 (混合記憶搜尋)
- **檔案**: `02_Memory_Context/mem0_provider.py` (新增), `07_PKG/graph_rag.py` (修改)
- **背景**: 目前記憶用 SQLite，KG 用 Neo4j/NetworkX。需要 Mem0 作為中間層提供 vector + graph 混合搜尋
- **要求**:
  - 新增 `mem0_provider.py`:
    - `class Mem0MemoryProvider`:
      - `__init__(config)`: 初始化 Mem0 client (`from mem0 import Memory`)
      - `add(content, user_id, metadata) -> str`: 存入記憶
      - `search(query, user_id, limit) -> List[MemoryItem]`: 向量搜尋
      - `get_all(user_id) -> List[MemoryItem]`: 列出所有記憶
      - `delete(memory_id)`: 刪除單筆
      - `update(memory_id, new_content)`: 更新
    - fallback: 如果 `mem0` 未安裝，退回使用現有 SQLite provider
  - 修改 `graph_rag.py` 的 `retrieve_context()`:
    - 新增 Step 0: 先用 Mem0 `search()` 做 vector 語意搜尋
    - 原本的 KG subgraph 作為 Step 2 的 graph-based 補充
    - 合併兩個來源的結果
- **commit**: `🧠 feat(memory): Mem0 hybrid vector/graph memory provider`

---

## Commit 順序 (建議)

```
A-1 → A-2 → A-3 → A-4 → B-1 → B-2 → C-1 → C-2 → D-1 → D-2 → E-1 → E-2 → F-1 → F-2 → F-3 → G-1 → H-1 → H-2 → H-3 → G-2
```

總計 **20 個 commit**，每個都是獨立可驗證的增量。
