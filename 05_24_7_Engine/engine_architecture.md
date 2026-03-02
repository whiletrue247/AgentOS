# 24/7 Engine 核心架構白皮書 (2025-2026 現狀)

為了讓 AgentOS 具備真正的「連續自主執行 (Autonomous Execution)」能力，我們捨棄了單一死循環 (while True) 腳本的舊思維。2025 年頂尖的 Agent 基礎設施，全面採用了 **事件驅動架構 (Event-Driven Architecture, EDA)**。

這個 `05_24_7_Engine` 的角色就是作業系統的行程總管，它不負責「思考」(思考是 API 加上 Prompt 的工作)，它負責**調度、保護、喚醒與限制**。

以下是 2025 年主流 AI 玩家 (如 LangGraph, AutoGen, CrewAI 生態系) 在構建 24/7 Engine 時，所使用的核心組件與標準工程術語。我們將這些機制整合起來，為 AgentOS 打造最強的心臟。

---

## ⚙️ 核心組件 (The Core Components)

### 1. 事件驅動總線 (Event-Driven Bus) 
*   **角色**：全身的神經網路。
*   **當前實務**：取代舊有「Agent 不停 Polling (輪詢) 檢查狀態」的低效做法。系統中任何事情（如信箱收到信、某個背景工作跑完、甚至是 Watchdog 發出警告），都會化作一個 `Event` 丟進總線。
*   **引擎行為**：Engine 處於睡眠狀態，直到總線上出現它感興趣的 `Event`，它才會喚醒對應的任務。這可節省 70%-90% 的運算資源。

### 2. 工作佇列 (Task Queue)
*   **角色**：非同步任務的停車場。
*   **當前實務**：當 Agent 被要求「去分析這 50 份 PDF」時，Engine 不會卡死在同一個 API 呼叫裡等待。
*   **引擎行為**：Engine 會自動將這個大任務拆解，丟入 Task Queue（實務上常使用 Redis/Celery 的概念）。Agent 可以並行 (Parallel) 處理，或是做完一個再從 Queue 裡拿（Dequeue）下一個。當遇到 API Rate Limit 時，未完成的任務會安靜地待在 Queue 裡排隊。

### 3. 排程器 (Cron) & 週期性工作 (Recurring Jobs)
*   **角色**：定時鬧鐘。
*   **當前實務**：用於完全不需要人類觸發的「自動駕駛模式 (Autopilot)」。
*   **引擎行為**：在 Engine 設定表裡寫入標準的 Cron 表示式（例如 `0 9 * * *` 每天早上九點）。時間一到，OS 自動實例化一個 Agent 任務包（例如去爬取最新新聞並總結），直接塞進 Task Queue 執行。

### 3.5 Multi-Agent 通訊匯流排 (Agent-to-Agent Bus)
*   **角色**：多 Agent 之間的郵差。
*   **當前實務**：當 Gateway 設定了多個專職 Agent（如 `code_agent`、`research_agent`）時，它們需要互相傳遞子任務和結果。
*   **引擎行為**：Event Bus 加上 `agent_id` 路由欄位。Agent A 完成子任務後，透過事件發送結果給 Agent B，Engine 的 Task Queue 負責排程。範例流程：
    1.  PM Agent 拆解任務 → Event Bus 發送 `{ to: "code_agent", payload: "寫 Flask API" }`
    2.  Task Queue 排入 code_agent 的工作佇列
    3.  code_agent 完成後回傳 `{ to: "pm_agent", payload: "代碼已推到 GitHub" }`
*   **記憶共享**：所有 Agent 共用同一個 Memory，但可透過 `metadata.custom_tags` 區分各 Agent 的私有記憶。

### 4. 心跳機制 (Heartbeat)
*   **角色**：主動探測與環境感知器。
*   **當前實務**：解決 Agent 的「被動性」。
*   **引擎行為**：這是一個輕量級的 Timer，例如每 30 秒觸發一次。Heartbeat 發生時，Engine 會掃描一遍「系統目前的變化 (System State Changes)」並形成一個極短的 Summary，悄悄傳給休眠中的 Agent 大腦：「現在沒事，但 CPU 溫度異常，你要不要去檢查一下？」讓 Agent 得以主動發表意見。

### 5. 任務級看門狗 (Task-Level Watchdog)
*   **角色**：冷酷無情的工安督導。與 `04_Sandbox` 的進程級 Watchdog 為父子關係（見下方層級說明）。
*   **當前實務**：專治「API 死鎖」、「無窮迴圈的 ReAct 幻覺」、「第三方工具超時」。
*   **引擎行為**：監控 Task Queue 裡正在跑的每一個任務進程。Watchdog 的所有觸發閾值均由 USER 在設定檔 (`engine_config`) 中自訂：

```yaml
# engine_config.yaml — USER 可自訂的安全參數
watchdog:
  api_call_timeout: 300        # 單次 API 呼叫最長等待秒數 (預設 5 分鐘)
  max_consecutive_errors: 10   # 連續呼叫同一工具失敗幾次後強制 Kill
  max_steps_per_task: 50       # 單一任務最大步數 (超過則暫停請求人類介入)
  human_escalation: true       # 超限時是否通知人類，還是靜默終止
```
*   **與 04 Sandbox Watchdog 的層級區別**：
    * `04` 的 Watchdog = **進程級** (Process-Level)：只管沙盒內單次指令的 Timeout (例如 `script.py` 跑超過 60 秒)。
    * `05` 的 Watchdog = **任務級** (Task-Level)：管整個任務的生命週期 (例如 Agent 總步數超過 50 步)。
    * 層級關係：`05 Watchdog` 是 `04 Watchdog` 的上級監督者。

### 6. 狀態機引擎 (State Machine & Checkpointer)
*   **角色**：任務的存檔點與時光機。
*   **當前實務**：SOTA 框架 (如 LangGraph) 的靈魂。任務隨時會被打斷（網路斷線、API 額度用盡）。
*   **引擎行為**：Agent 每執行完一個 Tool，Engine 就立刻做一次 `Checkpoint` (把 Memory 與執行流程圖的節點存入實體硬碟)。如果 Crash，系統重啟時能 100% 回到 Crash 前的一秒。

---

## 🛡️ 速率與配額安全閥 (Rate Limit & Governance)

2024 年底起，「防止 AI 破產與失控」成為了首要考量。這座 OS 必須內建對雲端預算的極致掌控。

### 1. 通道節流閥 (RPM / TPM Throttling)
*   **機制限流**：透過 `Token Bucket (權杖桶)` 或 `Sliding Window (滑動視窗)` 演算法，Engine 會截獲所有即將發往雲端的 API 請求。
*   **USER 可自訂**：

```yaml
# engine_config.yaml — 速率控制
rate_limit:
  rpm: 30                # 每分鐘請求上限 (Requests Per Minute)
  rpd: 1000              # 每日請求上限 (Requests Per Day)
  tpm: 100000            # 每分鐘 Token 上限
  on_limit_reached: sleep # sleep (等待) | queue (排隊) | notify (通知人類)
```
*   **保護措施**：當 Agent 瘋狂戳 API 時，超出設定的請求會被 Engine 硬性攔截，行為由 `on_limit_reached` 決定。

### 2. 步數預算與人類升級 (Step Budgets & Human Escalation)
*   **機制限流**：針對複雜任務的止損點。由 `watchdog.max_steps_per_task` 控制。
*   **保護措施**：走到上限時，Engine 強制暫停任務 (Suspend)，拋出 `Human Escalation Event` (請求人類介入)，等待主人在 Dashboard 按下「批准繼續」或「終止」。USER 也可以設定 `human_escalation: false` 改為靜默終止。

---

## ⚡ 網頁版 AI 對齊機制 (Web-AI Parity)

以下四項機制是讓 AgentOS 在體感上與 ChatGPT / Claude 網頁版完全對齊的關鍵。

### 1. 串流輸出 (SSE Streaming)
*   **痛點**：裸 API 預設是等全部生成完才一次回傳。使用者面對 30 秒的沉默會覺得 AI 壞了。
*   **OS 級實作**：Engine 在每次 API 呼叫時強制啟用 `stream=True`。收到的 Token 透過 SSE (Server-Sent Events) 即時轉發給 Messenger / Dashboard，實現文字一個一個蹦出來的體感。
*   **USER 可自訂**：
```yaml
streaming:
  enabled: true        # 關閉後退回全量回傳模式
  flush_interval_ms: 50  # 逐字推送間隔
```

### 2. 指數退避自動重試 (Auto-Retry with Exponential Backoff)
*   **痛點**：API 隨時可能回傳 `429 Too Many Requests` 或 `500 Internal Server Error`，網頁版會默默重試，使用者感覺不到。
*   **OS 級實作**：Engine 攔截所有可重試的錯誤碼 (429, 500, 502, 503)，自動執行指數退避——等 1 秒重試 → 等 2 秒重試 → 等 4 秒重試，最多 3 次。
*   **USER 可自訂**：
```yaml
retry:
  max_attempts: 3
  base_delay_seconds: 1
  backoff_multiplier: 2
  retryable_codes: [429, 500, 502, 503]
```

### 3. Prompt 快取 (Prompt Caching)
*   **痛點**：每次 API 呼叫都要重新發送 SOUL.md + 工具清單，如果 SOUL 有 3000 Token、跑 50 步就白燒 15 萬 Token。
*   **OS 級實作**：Gateway 自動偵測當前 Provider 是否支援快取 (Claude `cache_control`、Gemini `cachedContent`)。若支援，將 SOUL.md 與工具 Schema 標記為可快取，只在首次發送時計費。
*   **成本節省**：重複的 System Prompt 區塊節省高達 90% Token 費用。若 Provider 不支援快取，則靜默跳過無副作用。

> **⚠️ 實作備註**：OpenAI 的快取是自動的（prefix caching），開發者無法主動控制；Claude 用 `cache_control` 明確指定；Gemini 用 `cachedContent` API。Gateway 翻譯層需分別處理這三種差異。

### 4. 上下文壓縮器 (Context Compressor)
*   **痛點**：對話超過模型的 Context Window 上限時，裸 API 會直接報錯。網頁版默默在背景幫你做滾動摘要。
*   **OS 級實作**：Engine 在組裝 `messages` 陣列時，即時計算 Token 數量。當接近上限的 80% 時自動觸發壓縮：
    1. 將最早的 N 輪對話提取交給低成本模型生成摘要。
    2. 用摘要替換原始對話，釋放 Token 空間。
    3. 最近 3 輪對話永遠保留原文（避免失去近期上下文）。
*   **USER 可自訂**：
```yaml
context:
  compression_trigger: 0.8   # 達到 Context Window 的 80% 時觸發
  keep_recent_turns: 3       # 永遠保留最近幾輪原文
  summary_model: auto        # auto = 使用最便宜的可用模型做摘要
```

> **⚠️ 實作備註**：「用便宜模型做摘要」需要 Gateway 支援「中途插入 utility call」——即主 Agent 用 Claude Sonnet，但壓縮摘要用 GPT-4o-mini。此 utility call 不應計入主 Agent 的 Rate Limit，需在 Gateway 中獨立計數。Token 計數可用 `tiktoken`（OpenAI）或近似估算（字數 ÷ 4）。

---

*總結：ReAct 在這個 OS 架構下，不再是整個程式的迴圈結構，而純粹只是掛載於 `Action State` 節點上的一個「認知決策外掛 (Cognitive Plugin)」罷了。這個底層的 24/7 Engine 才是維護 Agent 體面與生存真正的英雄。*
