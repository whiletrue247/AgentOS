# Agent Base OS — 核心架構藍圖 (v5.0)

為 AI Agent 打造的作業系統級基礎設施平台。
**不是 APP，是 OS。** 貼上 API Key，3 分鐘內擁有一個高智商、全副武裝的 AI Agent。對新手友善，對資深玩家實用，所有參數可自訂。閒置 RAM < 60MB，峰值 < 150MB，無 GPU，零風扇。

> **🏛️ OS 最高設計準則：AgentOS 不禁止任何事情。它提供安全、經濟的預設值，但所有決策權歸 USER 所有。我們做的是平台載具，不是規則制定者。**

---

## 架構總覽：4 核心 + 2 平台

```
USER ↔ [Messenger / Dashboard]      ← 平台層：使用者接觸的介面
              ↓
       [04_Engine]  ←→  API          ← 心臟：API 路由 + 事件循環 + 安全閥
              ↓
       [03_Tool_System]  →  沙盒執行  ← 手腳：找工具 + 裝工具 + 安全執行
              ↓
       [02_Memory]  ←→  讀寫記憶      ← 海馬迴：統一記憶存取
              ↓
       [01_Kernel]  ←  SOUL.md       ← 靈魂：身份認同載入
```

---

## 核心層 (4 個不可移除的子系統)

### 1. `01_Kernel` — 靈魂載入器
OS 啟動時讀取根目錄的 `SOUL.md` 作為純文字，塞入 System Prompt。OS 不規定 SOUL.md 的內容結構——使用者可以寫任何想寫的東西。SOUL Generator（Dashboard 內建）可一鍵生成個性化靈魂。

### 2. `02_Memory` — 統一記憶數據元
定義 `UnifiedMemoryItem` 作為跨後端的萬用記憶格式。支援 SQLite、PgVector、Obsidian、Notion 等後端隨插即用。內建雙時序引擎、關聯拓樸、可選向量嵌入、行為反饋學習迴路。換資料庫 = 換 Provider，數據源永遠標準化。

### 3. `03_Tool_System` — 套件管理員 + 安全執行引擎 (合併原 03+04)
工具的完整生命週期在一個系統內完成：**發現 → 安裝 → 沙盒執行 → 結果回傳**。

| 子模組 | 職責 | 運行層級 |
|---|---|---|
| **Catalog** | 全球可用工具的 JSON 索引 + BM25 路由 | OS 特權層 |
| **Installer** | SYS_TOOL_INSTALL 三類安裝機制 | OS 特權層 |
| **Sandbox** | WASM / E2B / subprocess 隔離執行 | 沙盒隔離層 (囚犯看不到 Catalog) |
| **Truncator** | 輸出截斷 + 結果清洗 | OS 特權層 |

- 5 個不可卸載的系統工具：`SYS_TOOL_SEARCH`、`SYS_TOOL_INSTALL`、`SYS_TASK_COMPLETE`、`SYS_ROLLBACK`、`SYS_ASK_HUMAN`。
- 安全性靠 WASM/E2B 的物理隔離，不靠模組拆分。Sandbox 內的代碼無法觸碰 Catalog 或 Installer。
- 所有沙盒參數（網路策略、截斷比例、超時秒數）皆由 USER 在 `config.yaml` 自訂。

### 4. `04_Engine` — 心臟引擎 + API 閘道器 (合併原 05+Gateway)
整個 OS 的心臟。管理 API 呼叫的完整生命週期：**路由 → 發送 → 串流 → 重試 → 快取 → 限速**。

| 子模組 | 職責 |
|---|---|
| **API Gateway** | 多 Key 管理、Model-to-Agent 路由、Key 隱秘注入、自動 Failover、Model Adapter |
| **Event Loop** | asyncio 事件驅動、Task Queue、Cron 排程 |
| **A2A Bus** | Multi-Agent 間的事件路由與子任務分配 |
| **Rate Limiter** | RPM/TPM Token Bucket 節流 |
| **Streamer** | SSE 串流即時轉發給 Messenger / Dashboard |
| **Auto-Retry** | 指數退避重試 (429/500/502/503) |
| **Prompt Cache** | 自動利用 Claude/Gemini/OpenAI 的快取機制 |
| **Watchdog** | 任務級步數上限 + 死循環偵測 |
| **State Machine** | 任務狀態 + Checkpoint 可中斷復原 |

- 所有參數均由 USER 在 `config.yaml` 自訂。

---

## 平台層 (2 個使用者介面)

### 💬 Messenger (通訊軟體介面)
Telegram / Discord / LINE / Slack。雙向通訊 + 富媒體訊息 + 多頻道支援。

### 📊 Dashboard (輕量可視化面板)
純 HTML+JS 本地面板。任務總覽 + Token 花費追蹤 + Engine 狀態 + 設定編輯 + SOUL Generator。

---

## 🎨 使用者體驗層 (UX Layer) — 2027 新手友善設計

### 🚀 Onboarding Wizard (首次啟動引導)
使用者第一次執行 `python start.py` 時，OS 自動進入互動式引導模式：

```
Step 1/4 — 選擇 AI 模型
  [1] OpenAI (GPT-4o) — 最強通用
  [2] Anthropic (Claude) — 最擅長寫程式
  [3] 本地 Ollama — 免費，不需要網路

Step 2/4 — 輸入 API Key
  還沒有？點這裡申請：https://platform.openai.com/api-keys
  > sk-xxxxx
  ✅ 連線成功！剩餘額度：$18.50

Step 3/4 — 建立 AI 靈魂 (可跳過)
  → 開啟 Dashboard 的 SOUL Generator

Step 4/4 — 選擇通訊方式
  [1] Telegram Bot
  [2] Discord Bot
  [3] 只用終端機

🎉 設定完成！跟你的 Agent 說第一句話吧。
```

Wizard 自動生成 `config.yaml`。**新手永遠不需要手動編輯 YAML。**

### 💰 Cost Guard (預算守衛)
OS 內建透明的 Token 用量控制機制，以 **M (百萬 Token)** 為計量單位（不綁定任何貨幣，因為不同模型價格不同）：

- **執行前預估**：Agent 在執行複雜任務前，透過 `SYS_ASK_HUMAN` 向 USER 展示預估 Token 用量
- **即時計量**：Engine 紀錄每次 API 呼叫的 Token 數量，累計換算成 M
- **每日上限**：達到 `budget.daily_limit_m` 時自動停止並通知 USER
- **每月報表**：Dashboard 顯示每日 / 每週 / 每月的 Token 消耗圖表（分 Input / Output）

### 🗣️ 自然語言設定 (Natural Language Config)
USER 不需要打開 config.yaml。直接在 Messenger 裡說：

```
USER: 把我的每日預算設成 5 塊美金
Agent: ✅ 已更新 budget.daily_limit: 5.00

USER: 以後你回覆都用中文
Agent: ✅ 已更新 SOUL.md → 語言偏好：中文
```

### 📋 任務計畫可視化 (Plan Preview)
Agent 執行複雜任務前，先展示計畫再執行：

```
Agent:
  📋 執行計畫：
  1. 分析 5 個 Python 檔案結構
  2. 逐一轉譯成 TypeScript
  3. 建立 tsconfig.json
  4. 沙盒內編譯測試
  預估：~15 步，~0.08M Token，~5 分鐘
  
  繼續執行嗎？
```

這個行為由 SOUL.md 的本能引導 + `SYS_ASK_HUMAN` 確認機制配合實現。

### 📐 5 大 UX 交互原則

| 原則 | 說明 |
|---|---|
| **零設定即可用** | Onboarding Wizard 完成後，Agent 立即可工作，不需額外配置 |
| **透明無驚喚** | 每個動作的費用、風險、進度都透明可見 |
| **漸進式信任** | 初期多確認，隨使用經驗累積自動減少請示 |
| **人類永遠可介入** | `SYS_ASK_HUMAN` 確保 Agent 卡住時有正式求助管道 |
| **可撤銷可回滾** | `SYS_ROLLBACK` 確保任何設定變更都可逆轉 |

---

## 可安裝的生態工具 (從 Tool Catalog 安裝)

以下功能**不在 OS 核心中**，而是作為可選工具存在於 Catalog：

| 工具 | 說明 | 原屬子系統 |
|---|---|---|
| `ax_screen_reader` | macOS AXUIElement 語義樹讀取 | 原 06_External_Senses |
| `uia_screen_reader` | Windows UIA 語義樹讀取 | 原 06_External_Senses |
| `semantic_click` | 跨平台語義點擊 (AXPress/InvokePattern) | 原 06_External_Senses |
| `browser_cdp` | Chrome DevTools Protocol 網頁操控 | 原 06_External_Senses |
| `vision_screenshot` | Vision API 截圖流 (GPT-4o Vision) | 原 06_External_Senses |
| `context_compressor` | 上下文壓縮器 (用便宜模型做滾動摘要) | 原 05_Engine |
| `embedding_router` | 本地 Embedding 語意路由 (替代 BM25) | 原 03_Tool_Registry |
| `evolver_gep` | GEP 自我進化協議 (Memory → SOUL 畢業) | 外部生態 |
| `web_search` | 即時網路搜索 (Serper/Tavily) | 新增 |
| `file_parser_pdf` | PDF 轉純文字 | 新增 |

---

## 子系統管轄權定義 (Jurisdiction Charter)

| 操作類型 | 管轄 | 說明 |
|---|---|---|
| SOUL.md 載入 | `01_Kernel` | 純文字讀取，不解析結構 |
| 記憶讀寫與檢索 | `02_Memory` | 所有 Provider 的統一介面 |
| 工具發現、安裝、Schema 驗證 | `03_Tool_System` (OS 層) | Catalog + Installer |
| 工具實際執行 (bash, python) | `03_Tool_System` (Sandbox 層) | WASM / E2B / subprocess |
| API 呼叫路由與發送 | `04_Engine` | Gateway + Streamer |
| 速率控制 (RPM/TPM) | `04_Engine` | Rate Limiter |
| 任務生命週期管理 | `04_Engine` | Watchdog + State Machine |
| GUI 互動 (點按鈕、讀螢幕) | Tool Catalog 可選工具 | 需要才裝 |

---

## 統一設定檔 `config.yaml`

```yaml
# 靈魂
kernel:
  soul_path: ./SOUL.md

# API 閘道
gateway:
  providers:
    - name: openai
      api_key: sk-xxx
      models: [gpt-4o, gpt-4o-mini]
    - name: anthropic
      api_key: sk-ant-xxx
      models: [claude-3.5-sonnet]
    - name: ollama
      base_url: http://localhost:11434
      models: [mistral, llama3]
  agents:
    default: openai/gpt-4o
    code_agent: anthropic/claude-3.5-sonnet
    summary_agent: openai/gpt-4o-mini

# 引擎
engine:
  streaming: true
  retry: { max_attempts: 3, backoff_multiplier: 2 }
  rate_limit: { rpm: 30, tpm: 100000 }
  watchdog: { max_steps: 50, timeout_per_step: 300 }
  context: { compression_trigger: 0.8, keep_recent_turns: 3 }

# 預算守衛 (單位：M = 百萬 Token)
budget:
  daily_limit_m: 1.0        # 每日上限 1M Token
  warn_before_task: true     # 執行前預估 Token 用量
  track_input_output: true   # 分開追蹤 Input / Output Token

# 沙盒
sandbox:
  default_network: deny    # deny | allow
  timeout_seconds: 60
  truncation: { threshold: 2000, head_ratio: 0.1, tail_ratio: 0.2 }

# 通訊
messenger:
  telegram: { bot_token: "xxx", enabled: true }
  discord: { bot_token: "xxx", enabled: false }

# 面板
dashboard:
  port: 8080
  enabled: true
```
