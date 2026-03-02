# 03_Tool_System 統一工具系統架構

工具的完整生命週期在一個系統內完成：**發現 → 安裝 → 沙盒執行 → 結果回傳**。

合併了原 `03_Tool_Registry` 和 `04_Sandbox_Execution` 的職責。安全性靠 WASM/E2B 的物理隔離保障，不靠模組拆分。

---

## 兩層權限模型

```
┌─────────────────────────────────────┐
│  OS 特權層                           │
│  ├── Catalog (工具索引 + BM25 路由)   │
│  ├── Installer (三類安裝機制)         │
│  ├── Truncator (輸出截斷 + 結果清洗)  │
│  └── Sandbox 調度器 (選擇沙盒類型)    │
├─────────────────── 隔離牆 ───────────┤
│  沙盒隔離層                          │
│  └── 被執行的代碼：                   │
│      - 只能看到被 Mount 進來的工具     │
│      - 無法訪問 Catalog 或 Installer  │
│      - rm -rf 只影響沙盒內暫存檔      │
└─────────────────────────────────────┘
```

---

## Catalog (工具索引)

OS 出廠時 `tools/` 幾乎為空，只有一份輕量 `catalog.json` 索引。
索引可來自：本地靜態 JSON / 遠端 MCP Registry / 使用者自訂 `plugins/` 目錄。

路由預設使用 **BM25 零運算檢索**（可從 Catalog 安裝 `embedding_router` 替代）。

---

## 5 個不可卸載的系統工具

| 工具 | 功能 |
|---|---|
| `SYS_TOOL_SEARCH` | 搜索 Catalog 索引 |
| `SYS_TOOL_INSTALL` | 安裝工具到 Local Store |
| `SYS_TASK_COMPLETE` | 宣告任務完成並交付 |
| `SYS_ROLLBACK` | 回滾 SOUL.md / config.yaml 到歷史版本 |
| `SYS_ASK_HUMAN` | 向人類求助 / 請求資訊 / 確認高風險操作 |

### SYS_ASK_HUMAN 機制

Agent 在遇到無法獨自解決的阻礙時，透過 Messenger 向 USER 發送結構化求助：

```
SYS_ASK_HUMAN("我需要你的 Upwork 二步驟驗證碼來繼續登入")
→ Messenger 推播給 USER
→ USER 回覆驗證碼
→ Agent 取得回覆，繼續執行
```

適用場景：CAPTCHA、2FA、需要密碼、不確定是否刪除檔案、費用確認。
Agent 的行為反饋學習迴路會逐漸學會「什麼時候該問、什麼時候不該問」。

### SYS_ROLLBACK 機制

每次修改 `SOUL.md` 或 `config.yaml` 時，OS 自動備份到 `.history/` 資料夾（帶時間戳）。USER 或 Agent 可隨時呼叫：

```
SYS_ROLLBACK("soul", -1)     → 回到上一個 SOUL.md 版本
SYS_ROLLBACK("config", -3)   → 回到前 3 個 config.yaml 版本
SYS_ROLLBACK("list")         → 列出所有可回滾的歷史版本
```

回滾的對象跨越多個子系統（SOUL 屬 01、config 影響全局），但作為 OS 層級的系統操作指令，歸屬於 Tool System。

---

## 三類安裝機制

| 類型 | 安裝動作 | 範例 |
|---|---|---|
| **A. Schema-only (MCP)** | 只下載 JSON Schema，執行外包給 MCP Server | web_search, github_api |
| **B. Local Plugin (.py)** | 用 `importlib` 從 `plugins/` 載入 | pdf_parser, csv_reader |
| **C. System Package (pip)** | 在 Sandbox 內 `pip install`，避免污染宿主 | numpy, playwright |

---

## Sandbox 沙盒執行

依任務複雜度自動選擇沙盒類型：

| 條件 | 沙盒 | 說明 |
|---|---|---|
| 純 Python + 支援的庫 | Pyodide (WASM) | 本地瞬間執行，零延遲 |
| 需要 shell/npm/git | E2B 雲端 MicroVM | 完全隔離，需網路 |
| 離線模式 | subprocess + setrlimit | 基本資源限制 + tempdir 隔離 |

所有沙盒參數可在 `config.yaml` 設定：
- `sandbox.default_network: deny | allow`
- `sandbox.timeout_seconds: 60`
- `sandbox.truncation: { threshold, head_ratio, tail_ratio }`
- `sandbox.truncation: disabled`（USER 想看完整輸出）

> **⚠️ 實作備註 — Pyodide 庫限制**：部分 C 擴展庫不支援。OS 維護支援庫清單，不支援時自動升級到 E2B。

> **⚠️ 實作備註 — macOS 離線**：macOS 無 Linux 式 chroot。用 `subprocess.Popen` + `resource.setrlimit()` + `tempfile.mkdtemp()` 做基本隔離。

---

## SandboxProvider 抽象介面

沙盒技術演進快速（Docker → WASM → E2B → 未來新技術）。Tool System 內部透過 `SandboxProvider` 介面解耦：

```
class SandboxProvider:
    def execute(code, timeout, network) -> ExecutionResult
    def cleanup() -> None
```

換沙盒技術只需實現新的 Provider，不影響 Catalog 或 Installer。
