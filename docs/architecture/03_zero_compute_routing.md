# Tool Registry 零運算佈建架構 (Zero-Compute Routing 2025)

為了實現「掛載 1000 個工具卻不損耗 Mac 電池與 CPU 效能」的極致體驗，AgentOS 的 `03_Tool_Registry` 捨棄了傳統的「本地端高耗能神經網路 Embedding（向量運算）」。

根據 2025 年的 SOTA 實務與 MCP (Model Context Protocol) 伺服器端架構，我們採用以下兩種**零摩擦、零運算 (Zero-Compute)** 的 OS 級解決方案：

---

## 策略一：BM25 詞頻離散數學檢索 (The BM25 Router)

如果你非常討厭在本地跑神經網路（因為載入模型要吃 RAM，計算要吃 CPU/GPU 電池），最前沿的解法是回歸資訊檢索的經典：**BM25 演算法**。

*   **科學原理**：BM25 不需要神經網路。它純粹基於「詞頻 (TF)」與「逆向文件頻率 (IDF)」的離散數學統計。
*   **為什麼它在 2025 年重獲新生？**
    AI 開發者發現，工具的名稱與參數（例如 `sql_query`, `database`, `fetch_url`）其實是非常死板的「專有名詞」。**在專有名詞的比對上，BM25 的精準度往往輾壓神經網路 Embedding，而且運算成本幾乎是 0。**
*   **OS 級表現**：
    1. 你裝了 1000 個工具。OS 瞬間用 BM25 幫關鍵字建好統計索引（只需不到 1MB 的記憶體）。
    2. 主大腦要找工具時，OS 瞬間用 CPU 跑一個簡單的加減乘除數學式，0.0001 秒內找出 Top-3 關聯工具。
    3. **體感**：零延遲、筆電風扇絕對不會轉。

---

## 策略二：MCP 伺服器端路由 (Server-Side MCP Delegation)

如果連 BM25 都嫌佔用本地端資源，還有另一種更暴力的企業級架構：**讓雲端幫你扛**。

*   **痛點**：舊時代的 LangChain，是你必須把所有 JSON Schema 全部載入到本地 OS 的 RAM 裡面。
*   **2025 年 MCP 架構**：
    1.  **分離式架構**：你安裝的 1000 個工具，其實是註冊在一個遠端的 **MCP Server** 上。
    2.  **動態暴露 (Dynamic Exposure)**：你的本地 OS (`03_Tool_Registry`) 根本不知道那 1000 個工具的細節。本地 OS 只持有一把「萬能鑰匙 (Call MCP Server)」。
    3.  **雲端配對**：當大模型需要工具時，它把需求發送給遠端 MCP Server。MCP Server 自己的雲端強大算力會決定哪幾個工具適合，幫你算好、甚至直接在雲端執行完畢，然後只把「結果字串」透過標準化協定傳回你的 Mac。
*   **體感**：你的 Mac 幾乎不負責任何運算，它只是大模型與 MCP 雲端工具庫之間的一個「輕量級轉發路由器 (Lightweight Proxy)」。

---

### 總結

`03_Tool_Registry` 的預設路由方案是 **BM25 統計學檢索**（零資源、零延遲）與 **Server-side MCP 雲端外包**。這是最輕量、最適合大多數使用者的預設值。

> **OS 中立原則**：如果 USER 的硬體足夠強大（如 M4 Max + 128GB RAM），並且希望使用本地 Embedding 模型做語意檢索，OS 不禁止。使用者可從 Tool Catalog 安裝 `embedding_router` 工具（基於 sentence-transformers 等本地模型），與 BM25 並行使用或完全替代。OS 提供最經濟的預設值，但所有路由策略的選擇權歸 USER 所有。
