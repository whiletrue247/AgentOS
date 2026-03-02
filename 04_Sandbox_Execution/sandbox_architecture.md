# 04_Sandbox_Execution 沙盒防爆艙架構設計 (2025-2026 現狀)

在 AgentOS 架構中，大腦 (API) 是瘋狂的，工具表 (`03_Tool_Registry`) 是理性的發派員，而 `04_Sandbox_Execution` 則是**現實世界的堅固盾牌與防爆房**。

為了讓 AI 能毫無顧忌地寫 code、跑腳本、改系統，卻又不能把它信任到賦予 `sudo` 權限，2025 年頂尖的 Agent 基礎設施（如 E2B, Daytona, LangChain 的 Sandbox 模組）都實作了以下三大 OS 級防護機制：

---

## 🛡️ 防護一：物理隔離層 (The Isolation Layer)
**絕不能讓 LLM 生成的腳本，直接在宿主環境 (原生 MacOS/Windows) 用 `os.system()` 裸奔。**

*   **痛點**：AI 幻覺會導致致命的毀滅指令（例如誤刪專案、外洩 `.env` 檔案）。
*   **OS 級實作**：
    *   **本地閹割版容器 (Local Docker/WASM)**：收到執行指令時，沙盒子系統會瞬間啟動一個隔離的 Container 或 WebAssembly 虛擬機。將所需的檔案 Mount 進去，執行完畢後，把這個容器「連同垃圾檔案一起摧毀 (Ephemeral Environments)」。
    *   **網路預設策略 (Network Policy)**：OS 預設將網路關閉（親安全的預設值），但 USER 可在 `config.yaml` 中設定 `sandbox.default_network: allow` 來預設開啟網路。工具也可在 Schema 中聲明自己是否需要網路，覆寫預設值。

---

## ⏱️ 防護二：死鎖看門狗 (The Execution Watchdog)
**絕不能讓 LLM 卡住整個 24/7 Engine 的調度資源。**

*   **痛點**：AI 寫出無窮迴圈的爬蟲腳本，或是寫了一支需要人類輸入 `[Y/n]` 才能繼續的交互式 bash 指令，導致整個系統無聲無息地當機。
*   **OS 級實作：絕對無情的 Timeout 斬殺**：
    *   沙盒裡跑的任何一行代碼，都會掛上 `SIGKILL` 計時器（例：設定上限 60 秒）。
    *   當超時發生時，沙盒的看門狗會以最高權限斬斷該行程，並**回傳一封帶有教育意義的系統信號**給大腦：「*系統警告：你剛剛執行的 script.py 已超時 (Timeout=60s) 並被 OS 強制關閉。請檢查是否有無窮迴圈或等待輸入的 `input()` 函數。*」
    *   **目的**：讓 AI 自己知道痛，學會乖乖加上 `--yes` 標籤或修復循環邏輯。

---

## 🛑 防護三：輸出的頭尾截斷器 (The Context Truncator)
**這是在省下幾十萬 API 帳單，以及避免 LLM 智商崩潰的最關鍵元件。**

*   **痛點**：當 AI 執行 `npm install` 或是編譯大型專案時，終端機可能會一口氣噴出 10 萬字的 Warning 與安裝進度亂碼。如果你把這整包 `Stdout` 原封不動送回給歷史紀錄與 API，不僅 Token 當場爆炸，模型也會瞬間「忘記」一開始要做什麼任務（Lost in the Middle 現象）。
*   **OS 級實作：黃金段落擷取法 (Head-Tail Truncation)**：
    *   當沙盒回傳字串超過安全閥值（預設 2000 字元，可在 `config.yaml` 設定 `sandbox.truncation_threshold`）時：
    *   保留輸出最前面的 N% 與最後面的 M%（預設 `head_ratio: 0.1, tail_ratio: 0.2`，可在 `config.yaml` 調整）。
    *   USER 如果想看完整輸出，可設定 `sandbox.truncation: disabled`。
    *   中間所有囉嗦的廢話，OS 會無情地替換掉，變成：
        `... (47,000 characters truncated by the OS Sandbox for context safety) ...`
    *   **目的**：大模型只會看到精準、省錢、而且剛好夠它修 Bug 的那最後幾行關鍵錯誤訊息。

---

### 總結

`04_Sandbox_Execution` 是一個**可調節的安全防護網**。
OS 提供安全的預設值（斷網、截斷、超時），但所有參數皆由 USER 在 `config.yaml` 中自訂。OS 不替 USER 做安全決策，只提供合理的預設值。
