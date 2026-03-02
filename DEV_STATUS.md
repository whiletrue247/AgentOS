# AgentOS 開發進度追蹤

> **⚠️ 給 USER 的操作指南**
>
> 1. 每次只做 **一個 Task**
> 2. 切換到對應的 AI 後，複製以下 prompt 貼上：
>    ```
>    讀 Agent_Base_OS/DEV_STATUS.md 和 Agent_Base_OS/README.md
>    執行 Task [編號]
>    完成後更新 DEV_STATUS.md 的狀態
>    ```
> 3. AI 完成後，確認它更新了狀態欄位再切到下一個 AI
> 4. 按照表格順序往下做，不要跳號

---

## 當前狀態

- **當前 Phase**：✅ Phase 5 全部完成
- **當前 Task**：5.3 ✅ 已完成
- **下一個 Task**：Phase 6（如有）或準備釋出
- **指派給**：None

---

## Phase 1：地基 + 介面契約

> Claude 先行，定義所有介面。Gemini 後續按介面實作。

| # | Task | 指派 | 狀態 | 產出檔案 |
|---|---|---|---|---|
| 1.1 | 定義所有模組間的介面契約 (Interface Contracts) | Claude | [x] | `contracts/interfaces.py` |
| 1.2 | 實作 `config_schema.py` — config.yaml 的驗證 schema | Claude | [x] | `config_schema.py` |
| 1.3 | 實作 `01_Kernel/kernel.py` — SOUL.md 載入器 | Gemini | [x] | `01_Kernel/kernel.py` |
| 1.4 | 實作 `02_Memory/memory_manager.py` — Memory CRUD + Provider 介面 | Claude | [x] | `02_Memory/memory_manager.py` |
| 1.5 | 實作 `02_Memory/providers/sqlite.py` — SQLite Provider | Claude | [x] | `02_Memory/providers/sqlite.py` |
| 1.6 | 實作 `02_Memory/bm25_index.py` — BM25 檢索 | Claude | [x] | `02_Memory/bm25_index.py` |

## Phase 2：工具系統

| # | Task | 指派 | 狀態 | 產出檔案 |
|---|---|---|---|---|
| 2.1 | 實作 `03_Tool_System/catalog.py` — 工具索引 + BM25 路由 | Gemini | [x] | `03_Tool_System/catalog.py` |
| 2.2 | 實作 `03_Tool_System/sys_tools.py` — 5 個系統工具定義 | Gemini | [x] | `03_Tool_System/sys_tools.py` |
| 2.3 | 實作 `03_Tool_System/installer.py` — 三類安裝機制 | Gemini | [x] | `03_Tool_System/installer.py` |
| 2.4 | 實作 `03_Tool_System/sandbox.py` — SandboxProvider 抽象 | Gemini | [x] | `03_Tool_System/sandbox.py` |
| 2.5 | 實作 `03_Tool_System/sandbox_subprocess.py` — 本地 subprocess 沙盒 | Gemini | [x] | `03_Tool_System/sandbox_subprocess.py` |
| 2.6 | 實作 `03_Tool_System/truncator.py` — 輸出截斷 | Gemini | [x] | `03_Tool_System/truncator.py` |

## Phase 3：心臟引擎

| # | Task | 指派 | 狀態 | 產出檔案 |
|---|---|---|---|---|
| 3.1 | 實作 `04_Engine/gateway.py` — API Gateway + Model Adapter | Claude | [x] | `04_Engine/gateway.py` |
| 3.2 | 實作 `04_Engine/rate_limiter.py` — Token Bucket 節流 | Claude | [x] | `04_Engine/rate_limiter.py` |
| 3.3 | 實作 `04_Engine/streamer.py` — SSE 串流 | Claude | [x] | `04_Engine/streamer.py` |
| 3.4 | 實作 `04_Engine/engine.py` — 主事件循環 + Task Queue | Claude | [x] | `04_Engine/engine.py` |
| 3.5 | 實作 `04_Engine/cost_guard.py` — M Token 計量 + 預算守衛 | Claude | [x] | `04_Engine/cost_guard.py` |
| 3.6 | 實作 `04_Engine/state_machine.py` — 任務狀態機 + Checkpoint | Claude | [x] | `04_Engine/state_machine.py` |

## Phase 4：平台層

| # | Task | 指派 | 狀態 | 產出檔案 |
|---|---|---|---|---|
| 4.1 | 實作 `platform/messenger_telegram.py` — Telegram Bot | Gemini | [x] | `platform/messenger_telegram.py` |
| 4.2 | 實作 `platform/dashboard/` — 本地 Web 面板 | Gemini | [x] | `platform/dashboard/` |
| 4.3 | 實作 `01_Kernel/soul_generator.py` — SOUL 產生器 | Gemini | [x] | `01_Kernel/soul_generator.py` |
| 4.4 | 實作 `onboarding/wizard.py` — 首次啟動引導 | Gemini | [x] | `onboarding/wizard.py` |

## Phase 5：串接 + 端到端測試

| # | Task | 指派 | 狀態 | 產出檔案 |
|---|---|---|---|---|
| 5.1 | 串接 Engine ↔ Tool System ↔ Memory | Claude | [x] | `main.py` |
| 5.2 | 串接 Messenger ↔ Engine | Gemini | [x] | 修改 `main.py` |
| 5.3 | 端到端測試：透過 Telegram 下指令，Agent 自動搜索 + 寫碼 | 雙方 | [x] | `tests/e2e_test.py` |

---

## 每個 Task 完成後的 Checklist

完成一個 Task 後，當前 AI 必須：
1. ✅ 更新上方表格中的狀態 `[ ]` → `[x]`
2. ✅ 更新「當前狀態」區塊的下一個 Task 和指派
3. ✅ 確保代碼能獨立跑通（至少 import 不報錯）
4. ✅ 若有新增的介面或改動，更新 `contracts/interfaces.py`
