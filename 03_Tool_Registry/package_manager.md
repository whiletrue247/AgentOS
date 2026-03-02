# Tool Registry：OS 級套件管理員架構 (Package Manager)

`03_Tool_Registry` 不是一個塞滿工具的倉庫，而是一個 **brew / apt-get / pip**，外加一本目錄索引。

OS 出廠時 `tools/` 資料夾幾乎是空的。只有一份輕量的 Catalog 索引。AI 需要什麼工具，它自己判斷、自己安裝、自己使用。使用者完全不需要懂技術。

---

## 四層架構

| 層級 | 職責 | 類比 |
|---|---|---|
| **Tool Catalog (工具索引)** | 維護「全球可用工具清單」的輕量 JSON | `brew search` |
| **Installer (安裝引擎)** | AI 需要工具時，自動下載/啟用 | `brew install` |
| **Local Store (本地倉庫)** | 已安裝的工具存放位置，含版本資訊 | `/usr/local/Cellar/` |
| **BM25 Router (即時路由)** | 只對「已安裝」的工具做即時檢索 | `which` / `PATH` |

---

## 不可卸載的 3 個系統級工具

OS 出廠只預裝 3 個核心系統工具（如同 macOS 的 Finder / Terminal / Safari）：

| 工具 | 功能 | 為什麼不可卸載 |
|---|---|---|
| `SYS_TOOL_SEARCH` | 搜索 Tool Catalog 索引，查詢可用工具 | AI 需要它來發現新工具 |
| `SYS_TOOL_INSTALL` | 從 Catalog 安裝工具到 Local Store | AI 需要它來擴充武器庫 |
| `SYS_TASK_COMPLETE` | 宣告任務完成並提交成果 | Engine 需要它來收尾 |

所有其他工具（Web Search、File Parser、Image Generator、Code Executor）全部是**可選生態工具**。

---

## 三類安裝機制 (Install Categories)

`SYS_TOOL_INSTALL` 根據工具類型，走不同的安裝路徑：

| 類型 | 安裝動作 | 範例 | 開銷 |
|---|---|---|---|
| **A. Schema-only (MCP)** | 只下載 JSON Schema，實際執行外包給遠端 MCP Server | web_search_serper, github_api | 幾 KB，瞬間完成 |
| **B. Local Plugin (.py)** | 從 OS 的 `plugins/` 目錄用 `importlib` 動態載入 Python 檔 | pdf_parser, csv_reader | 本地秒載 |
| **C. System Package (pip)** | 需要 `pip install` 安裝依賴，**在 Sandbox 內執行以避免污染宿主** | numpy, playwright | 較慢，需網路 |

> **⚠️ 實作備註**：C 類安裝是最重的操作。Engine 應在安裝完成後通知使用者（透過 Messenger），且已安裝的依賴會被持久化在 Local Store 中，不需要重複安裝。

---

## AI 自主安裝流程

```
使用者：「幫我查今天台股收盤價」

AI (SOUL 本能)：
  → 檢查 Local Store：沒有 Web Search 工具
  → 呼叫 SYS_TOOL_SEARCH("web search")
  → Catalog 回傳：找到 "web_search_serper" (Serper API)
  → 呼叫 SYS_TOOL_INSTALL("web_search_serper")
  → OS 自動從 MCP Registry 載入 Schema 並寫入 Local Store
  → BM25 索引即時更新
  → 呼叫 web_search("台股 收盤價 今天")
  → 取得結果，回覆使用者

下次再遇到搜索需求 → 工具已在 Local Store，直接使用
```

---

## Tool Catalog 索引格式

```json
[
  {
    "tool_id": "web_search_serper",
    "name": "Web Search (Serper)",
    "description": "即時網路搜索引擎，支援 Google 搜索結果",
    "category": "search",
    "install_source": "mcp://serper.dev/search",
    "requires_api_key": true,
    "size_kb": 5
  },
  {
    "tool_id": "file_parser_pdf",
    "name": "PDF Parser",
    "description": "將 PDF 文件轉換為純文字",
    "category": "file",
    "install_source": "local://parsers/pdf",
    "requires_api_key": false,
    "size_kb": 50
  }
]
```

Catalog 可以來自：
- **本地靜態索引** (`catalog.json`，OS 出廠隨附)
- **遠端 MCP Registry** (即時從全球 MCP 伺服器拉取最新工具)
- **使用者自訂** (在 Local Store 手動放入自己寫的工具)

---

## 設計哲學

> **APP 思維** = 出廠時幫你裝好一切，越多越炫越好。
> **OS 思維** = 出廠時只給你一個乾淨的系統 + 套件管理員，讓住在裡面的 AI 自己決定裝什麼。
