# AgentOS 核心記憶數據元研究報告 (2025-2026 現狀)

為了打造一個「隨插即用、無縫切換」的 AgentOS 記憶底層，我們對目前（2025-2026）最具代表性的 AI Agent 記憶框架與**最受開發者/用戶歡迎的本地記憶後端**進行了深度解剖。

無論廠商使用何種炫酷的術語（Temporal Graph, Vector RAG, Memory Layer），或是極客玩家偏好哪種筆記軟體（Notion, Obsidian, SQLite），其底層的**數據源 (Data Primitives)** 都萬變不離其宗。

本報告統整了五大主流流派、對應的開源/商業套件與常見後端，以及它們真正在硬碟裡儲存的欄位，並以此推導出 AgentOS 的「大一統數據元結構」。

---

## 🔍 主流記憶流派、套件與熱門後端解析 (2025-2026)

### 1. 智慧型記憶層 (SaaS/Managed Memory Layer)
* **代表套件**：**Mem0**, **Zep** (早期版本)
* **核心概念**：提供 REST API，開發者把對話丟過去，平台自動做總結、分類與提取使用者的喜好 (Preferences)。
* **底層數據源 (Data Primitives)**：
  * `id`: 記憶區塊的 UUID。
  * `user_id` / `session_id`: 歸屬的實體。
  * `content`: 萃取後的純文字事實或摘要，例如 "User prefers Python".
  * `created_at` / `updated_at`: 時間戳記。
  * `category` / `tags`: 分類標籤。

### 2. 時序型知識圖譜 (Temporal Knowledge Graph)
* **代表套件**：**Zep Graphiti**, **Neo4j + GenAI**, **FalkorDB**
* **核心概念**：揚棄純平面的向量，把每次事件萃取成有方向的「點與線」，並且具有時間軸概念。
* **底層數據源 (Data Primitives)**：
  * **節點 (Nodes)**：
    * `node_id`, `type`, `attributes`
  * **邊緣 (Edges / Relationships)**：
    * `source_id`, `target_id`, `fact`, `t_valid` / `t_invalid` (雙重時序)

### 3. 單一檔案即資料庫 (Local-First / Single-Binary SQL)
* **代表熱門後端**：**SQLite**, **SQLite-vec** (向量擴充), **FTS5** (全文檢索), **CortexaDB**
* **核心概念**：開發者與開源圈最愛。無伺服器、極致隱私、零維運（Zero-operations）。整套 RAG 系統與對話紀錄全部塞在一個 `.sqlite` 檔案裡。
* **底層數據源 (Data Primitives)**：
  * **明確的欄位 (Columns)**：`id`, `session_id`, `role`, `content`, `timestamp`.
  * 若啟用擴充，還會有隱藏的 `embedding` (BLOB) 欄位與 `fts_index` 虛擬表。

### 4. 個人知識庫與雙鏈筆記 (PKM / Human-Readable Memory)
* **代表熱門後端**：**Notion**, **Obsidian**, **Logseq**
* **核心概念**：不只要給 AI 看，還要「人類可讀、可編輯 (Human-auditable)」。Agent 透過 MCP (Model Context Protocol) 協議，直接把使用者的筆記本當作長期大腦。
* **底層數據源 (Data Primitives)**：
  * **Obsidian (Markdown 生態)**：
    * `filename.md` (作為 ID)
    * `frontmatter / YAML`: Meta-data (如 `tags`, `aliases`, `date`).
    * `body`: 純文字內容。
    * `[[Wikilinks]]`: 實體雙向連結（等同於 Graph 的 Edges）。
  * **Notion (Database 生態)**：
    * `page_id`
    * `Properties`: 結構化欄位 (Select, Date, Relation).
    * `Blocks`: 頁面內的區塊內容。

### 5. 企業級統一資料庫 (Unified Operational AI Database)
* **代表熱門後端**：**PostgreSQL + pgvector / pgvectorscale**
* **核心概念**：2025 年的企業終極解答。不想管圖譜、向量、關聯庫三套系統，直接用最強大的開源關聯資料庫全包。
* **底層數據源 (Data Primitives)**：
  * 混合儲存：同一個 Table 裡同時有 JSONB (存 Metadata)、VECTOR 欄位 (存 Embedding)、以及 TEXT (存原始字串)。

---

## 🏆 AgentOS 通用超級數據元 (Unified System Primitive)

統合上述所有的前沿科技與極客最愛的後端（從 SQLite 到 Obsidian），一套不被特定資料庫綁架的 OS 級記憶數據，必須兼顧 **文字特徵 (Vector)**、**實體關係 / 雙向連結 (Graph/Obsidian)** 以及 **時間與屬性 (SQL/Notion)**。

只要我們的記憶套件介面，都接受並回傳以下這個標準的 `UnifiedMemoryItem` (JSON/Pydantic Model)，用戶就能在任何資料庫之間無縫讀取與遷移：

```json
{
  "memory_id": "uuid4_或_Obsidian的檔名",

  // 1. 實體與歸屬 (配合 Mem0 / SQLite)
  "session_id": "對話或任務的 ID",
  "agent_role": "產生這筆記憶的代理人 (user / assistant / system)",

  // 2. 內容核心 (配合 Vector DB / Notion Blocks / Obsidian files)
  "content": "記憶的純文本實體 (如代碼片段、對話紀錄、事實陳述)",
  "content_type": "enum: [episode, fact, state_snapshot, rule, markdown_note]",

  // 3. 雙時序引擎 (致敬 Zep Graphiti 2025)
  "temporal": {
    "t_created": "系統生成的 UNIX 時間戳",
    "t_valid": "該事實生效時間",
    "t_invalid": "該事實失效時間 (若為 null 則持續生效)"
  },

  // 4. 關聯拓樸圖 / 雙向連結網路 (配合 Graph DB / Obsidian Wikilinks / Notion Relations)
  "relationships": [
    {
      "target_memory_id": "uuid4_或_另一個筆記檔名",
      "relation_edge": "supersedes | references | caused_by (例如：這筆筆記 [[references]] 了某個專案)"
    }
  ],

  // 5. 擴充插槽 (配合 VectorDB 必備的過濾器 / Notion Properties / Obsidian YAML Frontmatter)
  "metadata": {
    "source_file": "如果有實體檔案來源",
    "importance": 0.8, // 權重，用於 Garbage Collection
    "custom_tags": ["auth", "security", "planning"],
    "kv_pairs": {} // 任何未在上方定義的屬性，通通塞進這個 JSONB 字典
  },

  // 6. 向量嵌入插槽 (配合 PgVector / SQLite-vec / Chroma / FAISS)
  // 此欄位由 Provider 在寫入時自動計算填入，讀取時由 Provider 負責解碼。
  // 如果當前後端不支援向量 (如純 Obsidian)，則此欄位為 null。
  "embedding": null,  // [float] | null — 維度由 Provider 決定 (e.g. 1536 for OpenAI, 384 for MiniLM)

  // 7. 後端提示 (Provider Hint)
  // 當資料從 A 後端遷移到 B 後端時，此欄位告訴新 Provider 原始來源。
  "provider_hint": {
    "origin_backend": "sqlite-vec",    // 原始儲存後端
    "embedding_model": "text-embedding-3-small",  // 使用的嵌入模型 (若需要重新計算向量時參考)
    "embedding_dimensions": 1536
  }
}
```

### 💡 如何實現「數據庫拔插不轉檔」？
對 OS 核心來說，所有的歷史軌跡就是一個無窮盡的 `UnifiedMemoryItem` 陣列（底層存在一個 `.jsonl` 或你的 Obsidian Vault 裡作為 Ground Truth）。
當用戶掛載不同的 Backend (如 `PgVectorProvider`, `SQLiteProvider` 或 `ObsidianProvider`) 時：
*   **你裝 SQLite 套件**：套件會把這個 JSON 拆進 3 個表格。
*   **你裝 Obsidian 套件**：套件會把 `metadata` 轉成 YAML Frontmatter 寫在 `.md` 檔頭，把 `relationships` 變成 `[[Wikilinks]]`，把 `content` 寫在內文。
* **轉換資料庫，就是換一個建立索引的 Provider，數據源本身依然保持純淨且標準化。**

### 🧬 Embedding 與 Provider Hint 的遷移策略
當使用者從 A 後端遷移到 B 後端時，`provider_hint` 提供了關鍵的遷移上下文：
*   **A = SQLite-vec (本地向量) → B = PgVector (雲端向量)**：
    *   如果兩者使用相同的 `embedding_model`，向量可以直接搬遷 (零成本)。
    *   如果 B 使用了不同維度的模型，B Provider 會讀取 `provider_hint.embedding_model`，判定需要重新計算，自動排入背景任務重新 embedding。
*   **A = PgVector → B = Obsidian (純文字)**：
    *   Obsidian Provider 不支援向量。它會忽略 `embedding` 欄位，只遷移 `content` 和 `metadata`。
    *   `provider_hint` 會被保留在 Obsidian 的 YAML Frontmatter 中，以便未來回遷時可以恢復向量。
*   **新安裝的後端觸發自動索引**：
    *   當一個全新的 Provider 被掛載時，它會掃描所有 `embedding: null` 的記憶項目，自動排入 `05_24_7_Engine` 的 Task Queue，在背景以 Rate-Limited 的速度呼叫 Embedding API 填入向量。使用者不需要手動操作。

---

## 🧠 行為反饋學習迴路 (Behavioral Feedback Loop)

Agent 的自主權等級（該不該中途打擾使用者？）不應該被硬編碼在 SOUL.md 裡。
不同使用者有不同偏好，且偏好會隨時間演化。正確的做法是：**讓 Agent 從互動中自己學。**

### 機制原理

| 步驟 | 執行者 | 動作 |
|---|---|---|
| 1. 觀察 | Engine | 從 LLM 回覆的 Tool Call 中讀取結構化的 `preference_signal` 欄位 |
| 2. 寫入 | Engine → Memory | 將偏好存為 `content_type: "fact"` 的 `UnifiedMemoryItem`，設定高 `importance` |
| 3. 召回 | Engine | 每次組裝 API Context 前，從 Memory 撈出高權重的行為偏好 fact，塞入 System Prompt 尾端 |
| 4. 適應 | LLM | 模型讀到偏好 fact 後，自動調整行為（少問 / 多問 / 先做再報告） |
| 5. 強化/衰減 | Engine | 使用者未抱怨 → importance 微升；30 天未觸及 → importance 自然衰減 |

> **⚠️ 實作備註**：步驟 1 的「觀察」不能用自由文字解析（太脆弱）、也不能額外呼叫一次 API 做情緒分析（太貴）。務實做法是讓主 LLM 在回覆的 Tool Call 中夾帶一個可選的結構化欄位：
> ```json
> { "preference_signal": { "user_wants_less_questions": true } }
> ```
> Engine 只需解析這個 JSON 欄位，開銷為零。

### 寫入 Memory 的範例

```json
{
  "memory_id": "pref_001",
  "content": "USER 明確表示不喜歡被中途請示，偏好 Agent 全自動執行後才回報結果",
  "content_type": "fact",
  "temporal": { "t_created": "2026-03-03T02:25:00Z", "t_valid": "2026-03-03T02:25:00Z", "t_invalid": null },
  "metadata": { "importance": 0.95, "custom_tags": ["user_preference", "autonomy"] }
}
```

### 使用者不需要做任何設定

Agent 的初始行為是中性的（完成後回報，不中途打擾）。
隨著互動累積，Memory 裡會自然沉澱出這位主人專屬的「行為輪廓」。
同一份 SOUL.md、同一個 OS，但不同的 Memory = 不同性格的 Agent。

