# 06_External_Senses 原生視覺與操控架構 (Zero-Cost Native Senses 2025)

對於一個能夠控制實體電腦的 AgentOS 來說，**「Computer Use (電腦操控)」** 是終極的武力展示。目前市場上有兩種主流方案：

| 方案 | 優點 | 缺點 | 適用場景 |
|---|---|---|---|
| Vision API (截圖流) | 通用性最高，什麼都能看 | 貴 (每次截圖 ~$0.01)、慢、可能看錯 | 遊戲、Canvas 繪製的 App |
| 原生無障礙樹 (AX/UIA) | 免費、瞫間、100% 精準 | 只能看原生 UI 元素 | 大部分日常 App |

AgentOS 的立場：**OS 不替 USER 選擇**。預設採用免費的原生無障礙樹，但 Vision API 可作為工具從 Tool Catalog 安裝，USER 想用就裝。

如精明的開發者所言：「Mac 本身就已經有無障礙 (Accessibility) 功能了，為什麼不直接用？」

為了提供最佳的預設體驗，AgentOS 的 `06_External_Senses` 子系統預設採用 **「原生語義樹 (Native Semantic Tree)」** 架構，零成本且極度精準。

---

## 👁️ 第一層：零成本的語義視覺 (The Zero-Cost Semantic Eyes)

大模型擅長的是讀「文字結構」，而不是看「像素」。我們透過呼叫作業系統的最底層 API，直接把畫面上的按鈕變成文字交給大模型。

### 1. 跨平台原生無障礙樹 (Native Accessibility APIs)
*   **科學原理**：現代作業系統為了視障人士與自動化測試，都設計了極度強大的 Accessibility API。畫面上任何一個原生的 App，其視窗內的每一個按鈕、輸入框，在記憶體裡都有一棵「UI 元素樹 (UIElement Tree)」。
*   **OS 級實作 (跨平台支援)**：
    *   **macOS**: 使用 `AXUIElement` 框架 (透過 PyObjC 或 Swift 橋接)。
    *   **Windows**: 使用微軟的 `UI Automation (UIA)` 框架 (透過 `pywinauto` 或 C# 橋接)。這是微軟 2025 年推動 AI GUI 控制的核心底層。
    *   **Linux / Ubuntu**: 使用 `AT-SPI` (Assistive Technology Service Provider Interface) 框架，廣泛支援 GNOME, KDE 等桌面環境。
    *   當 AI 說「我要看現在 Slack 的視窗」，作業系統底層會調用對應平台的 API，瞬間抓取 UI 樹。
    *   **轉換**：OS 把這棵樹轉成一段極度精簡且跨平台的 JSON 或 Markdown 清單：
        ```json
        [
          {"id": 1, "role": "AXTextField", "description": "Search channel", "value": ""},
          {"id": 2, "role": "AXButton", "description": "Send message", "enabled": true}
        ]
        ```
    *   **成本與速度**：這段純文字傳給 LLM 只花不到 200 個 Token (約 $0.0001)，而且精準度是 100%（不會有視覺模型看錯字的問題）。

### 2. 瀏覽器原生 DOM 萃取 (Chrome DevTools Protocol / Playwright)
*   **科學原理**：對於網頁，DOM Tree 就是它的靈魂。
*   **OS 級實作**：當遇到網頁操作時，OS 透過 CDP (Chrome DevTools Protocol) 抽出網頁的 `Accessibility Node` 或是經過清洗的精簡 `DOM`，把雜亂的 CSS 和 Script 全部去掉，只留下帶有 `aria-label` 的按鈕和文字，餵給 LLM 判斷。

---

## ✋ 第二層：絕對精準的神經反射動作 (Deterministic Actuation)

既然我們不用截圖來找座標 (X, Y)，我們點擊按鈕的精準度就可以達到 100%。

### 1. 繞過滑鼠軌跡的跨平台「語義點擊 (Semantic Click)」
*   **痛點**：用 `pyautogui` 去模擬滑鼠移動並點擊 `(x: 500, y: 300)`，很容易因為視窗稍微被挪動、或是螢幕解析度改變而點錯（點到刪除鍵就悲劇了）。
*   **OS 級實作 (跨平台神經反射)**：
    *   當 LLM 回覆：「*請點擊剛才清單裡的 `id: 2` (Send message) 按鈕*」。
    *   `06_External_Senses` 會根據當下系統呼叫對應的底層觸發器：
        *   **macOS**: 發送 `AXPress` 訊號給指定的 `AXUIElement`。
        *   **Windows**: 發送 `InvokePattern.Invoke()` 給 UIA 節點。
        *   **Linux**: 呼叫 AT-SPI 介面的 `DoAction()` 事件。
    *   **體感**：滑鼠游標根本不用移動過去，那個按鈕就會像被魔法按下一樣觸發。這是不受螢幕解析度干擾的**絕對精確控制**。

### 2. fallback 機制：Set-of-Mark 視覺網格 (The Vision Fallback)
*   **防錯設計**：如果遇到某些寫得很爛的 Electron 軟體或是不支援 Accessibility API 的舊遊戲，怎麼辦？
*   **OS 級實作**：這時候才啟動備用方案。OS 會截圖，並在本地用一個超輕量的傳統視覺模型（如 OpenCV 邊緣偵測）把看起來像按鈕的地方框起來打上數字 `[1], [2], [3]`，再做傳統的視覺點擊。只有在這個最壞的情況下，我們才會動用比較貴的截圖法。

---

### 總結：多層可選的感知策略

`06_External_Senses` 提供多層可選的感知策略：

1. **預設路線（免費）**：原生 AX/UIA/AT-SPI 無障礙樹 → 零 Token 成本，100% 精準
2. **網頁路線（免費）**：CDP / Playwright DOM 萃取
3. **Fallback（低成本）**：Set-of-Mark 視覺網格 + OpenCV
4. **可安裝擴充（付費）**：Vision API 截圖流（從 Tool Catalog 安裝 `vision_screenshot` 工具）

OS 不禁止任何方案，只提供最經濟的預設值。USER 的預算充足且需要 Vision 的通用性？裝就對了。
