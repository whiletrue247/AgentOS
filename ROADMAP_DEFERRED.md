# AgentOS — 未來路線圖 (Deferred Features)

本文檔記錄已規劃但暫緩實施的功能，供工程團隊未來參考。

---

## 1. Deep OS Hook — 原生作業系統整合

### 現狀
- `06_Embodiment/desktop_runtime.py`: pyautogui 工具層
- L0/L1/L2 風險分級已實作
- macOS `screencapture` / AppleScript 基本支援

### 目標
- **macOS Accessibility API**: 語意級操作 (「點擊名為 X 的按鈕」)
- **Windows UIAutomation**: Win32 API 原生控制
- **跨裝置接力**: 手機任務 → 桌面繼續 (Handoff)

### 暫緩原因
- 平台特定投入巨大 (每個 OS 版本可能 break)
- 2026 趨勢偏向 browser-first Agent (Claude Computer Use, Google Mariner)
- macOS 沙盒限制日益嚴格

### 實施路徑 (未來)
```
06_Embodiment/
├── desktop_runtime.py    ← 現有
├── macos_accessibility.py   ← TODO: AXUIElement API
├── windows_uiautomation.py  ← TODO: Win32 UIAutomation
└── handoff_manager.py       ← TODO: 跨裝置 session 接力
```

---

## 2. 真 MicroVM Sandbox — Firecracker/gVisor

### 現狀
- Docker 容器沙盒 (強化版: --read-only, --cap-drop=ALL 等)
- E2B Cloud Sandbox Provider (`sandbox_e2b.py`) 已就緒

### 目標
- **Firecracker MicroVM**: AWS 等級的 microVM 隔離
- **gVisor**: 用戶態 Linux kernel，無需完整 VM

### 暫緩原因
- 運維成本極高 (需要 KVM 支援)
- macOS 不支援 Firecracker
- E2B Cloud 已提供同等隔離度且零運維

### 實施路徑 (未來)
```
03_Tool_System/
├── sandbox_docker.py     ← 現有 (生產用)
├── sandbox_e2b.py        ← 已實作 (雲端 MicroVM)
├── sandbox_firecracker.py  ← TODO: 自建 MicroVM (Linux only)
└── sandbox_gvisor.py       ← TODO: gVisor runtime
```

---

## 3. Plugin Marketplace 經濟

### 現狀
- 工具系統支援 `local_plugin` / `schema_only` / `mcp_server`
- Zero Trust ACL 控制工具權限

### 目標
- 插件商店 (發布、搜尋、安裝、評分)
- 插件沙盒隔離 (每個插件獨立 Docker 容器)
- 付費插件 + 收入分潤

### 暫緩原因
- 需要用戶生態才有意義
- 支付系統整合複雜
- 目前階段應專注核心 Agent 能力

### 實施路徑 (未來)
```
09_Marketplace/
├── registry.py          ← TODO: 插件註冊表
├── installer.py         ← TODO: 安全安裝流程
├── sandbox_per_plugin.py ← TODO: 插件級沙盒
└── rating_system.py     ← TODO: 評分與回饋
```

---

## 4. 完整 Agent Simulator

### 現狀
- Event Trace (`event_trace.py`) 已支援事件持久化和 Rollback
- Dashboard 有基本成本統計

### 目標
- 單步 Debug: 逐步執行 ReAct loop，每步暫停檢視
- 完整 Replay: Mock LLM 回應，重放完整對話
- A/B Test: 同一輸入用不同 system prompt 比較

### 暫緩原因
- 需要 Mock 整個 LLM 回應管線
- UI 工作量大 (但 Event Trace 已提供數據基礎)

### 實施路徑 (未來)
```
08_Platform/dashboard/
├── server.py           ← 現有
├── trace_view.py       ← TODO: 事件回放 UI
├── debug_stepper.py    ← TODO: 單步 Debug 控制器
└── ab_tester.py        ← TODO: A/B 測試框架
```

---

## 更新日誌
- **2026-03-03**: 初版路線圖建立
