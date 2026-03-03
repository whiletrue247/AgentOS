# 零資源沙盒架構白皮書 (Zero-Resource Sandboxing 2025)

傳統的 Docker 雖然提供了良好的隔離性，但在 2025 年高頻率、碎片化的 AI Agent 任務中，Docker 暴露出一個致命缺點：**啟動太慢、極度耗費本機 RAM 與 CPU 資源**。

對於在 Mac 筆電上運行的個人 AgentOS，如果 AI 每修改一次代碼就要啟動一個背景 Docker，電腦的風扇不僅會狂轉，電池也會迅速耗盡。

為了實現「極致輕量、瞬間啟動、零資源霸佔」的防爆艙，2025 年最前沿的 Agent 架構全面轉向以下三種次世代沙盒技術：

---

## 1. WebAssembly (WASM) / WASI：微秒級的極致輕量
*   **科學原理**：WASM 最初是為瀏覽器設計的二進位指令格式。現在透過 WASI (WebAssembly System Interface)，它可以直接在任何作業系統上運行。
*   **優勢**：
    *   **體積與速度**：啟動時間是**微秒級 (Microseconds)**，幾乎沒有任何冷啟動延遲。
    *   **零資源霸佔**：不需要虛擬化整個 Linux 核心，記憶體占用極低。
    *   **預設絕對安全 (Default Deny)**：WASM 採用「能力導向安全 (Capability-based Security)」，預設完全禁止讀寫硬碟與網路，必須由 AgentOS 顯式賦予極狹窄的權限。

## 2. Pyodide：將 Python 塞進 WebAssembly
*   **科學原理**：這是 CPython 直譯器的 WASM 編譯版本。
*   **優勢**：如果你的 Agent 只需要跑 Python 腳本（例如資料清洗、畫圖表），OS 完全不需要安裝 Docker。OS 可以直接在底層瞬間啟動一個 Pyodide 環境。
*   **LangChain 實務**：LangChain Sandbox 目前大量利用 Pyodide 來執行不受信任的 Python 程式碼，確保 AI 寫的代碼絕對不會碰觸到你 Mac 上真實的檔案系統與環境變數。

## 3. MicroVMs (Firecracker) 與雲端沙盒 (E2B)
*   **科學原理**：如果你需要完整的 Linux 環境（不只 Python，還要裝 Node.js, 跑 Git），但又不想要 Docker 的笨重。AWS 開源的 Firecracker MicroVMs 是最佳解答。它在 150 毫秒內就能啟動一個帶有獨立 Linux Kernel 的硬體級隔離虛擬機，記憶體負擔不到 5MB。
*   **企業級 / 零本地運算解法 (E2B 平台)**：
    *   **E2B (Execute to Build)** 平台是專為 AI Agent 打造的雲端沙盒。
    *   **OS 級運作**：你的 Mac 完全不需要安裝 Docker 或 VM。當 AI 生成了一段破壞性腳本，AgentOS 的 `04` 模組透過 E2B SDK，瞬間在**雲端伺服器**利用 Firecracker 開啟一個隔離微型虛擬機。
    *   代碼在雲端編譯、執行、報錯，最後 E2B 把 `Stdout` 傳回你的 Mac。
    *   **體感**：你的 Mac 本機 `0 資源損耗`，所有重計算、安裝套件的髒活與資安風險，全部由雲端吸收。

---

### 總結：給 AgentOS 企業級的輕盈感

未來的 `04_Sandbox_Execution` 不應該強制依賴笨重的 Docker Desktop。

針對不同的破壞強度，OS 應具備自動降級/升級的沙盒策略：
1.  **純 Python 運算** 👉 瞬間丟入本地的 `Pyodide (WASM)` 執行 (耗損趨近於零)。
2.  **複雜的系統指令或編譯** 👉 呼叫 `E2B` 將破壞力與運算力完全外包給雲端 MicroVM。
3.  **離線降級** 👉 本地 `subprocess` + 基本資源隔離。

> **⚠️ 實作備註 — Pyodide 庫限制**：Pyodide 並非所有 Python 庫都支援。依賴 C 擴展的庫（如 `requests`、部分 `beautifulsoup` 功能）可能無法運行。OS 應維護一份「Pyodide 支援庫清單」。當 Agent 代碼 import 了不支援的庫時，自動升級到 E2B 雲端沙盒。

> **⚠️ 實作備註 — macOS 離線降級**：macOS 沒有 Linux 式的 chroot/cgroup/namespace。`sandbox-exec` 已被 Apple 標記 deprecated。務實做法：使用 `subprocess.Popen` + `resource.setrlimit()` 做 CPU/Memory 上限 + `tempfile.mkdtemp()` 做目錄隔離。這不是真正的容器隔離，但足以防止無窮迴圈和記憶體爆炸。

這才是 2025 年真正在消費者筆電上能夠流暢運行的「不插電沙盒防護網」。
