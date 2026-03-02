# Changelog

All notable changes to AgentOS will be documented in this file.

## [v4.0.0] — 2026-03-03

### 🎉 Initial Release — AgentOS v4.0 "Foundation"

> 完整的 AI Agent 作業系統基礎設施，4 核心 + 2 平台架構。

### ✨ Core Modules (4 核心子系統)

#### 01_Kernel — 靈魂載入器
- `kernel.py` — SOUL.md 純文字載入，作為 System Prompt 注入 Engine
- `soul_generator.py` — 透過 LLM 一鍵生成個性化 SOUL.md

#### 02_Memory — 統一記憶數據元
- `memory_manager.py` — 統一介面，支援 CRUD、搜索、上下文取得
- `providers/sqlite.py` — SQLite + FTS5 (BM25) 全文檢索 Provider
- `bm25_index.py` — 獨立的 BM25 檢索引擎

#### 03_Tool_System — 工具系統
- `catalog.py` — 工具索引 + BM25 語意路由
- `sys_tools.py` — 5 個不可卸載的系統工具 (SEARCH / INSTALL / TASK_COMPLETE / ROLLBACK / ASK_HUMAN)
- `installer.py` — 三類安裝機制 (schema_only / local_plugin / system_package)
- `sandbox.py` — SandboxProvider 抽象層
- `sandbox_subprocess.py` — 本地 subprocess 沙盒 (macOS/Linux)
- `truncator.py` — 輸出截斷 + 結果清洗

#### 04_Engine — 心臟引擎
- `engine.py` — 主事件循環 + ReAct Loop + Task Queue
- `gateway.py` — API Gateway + Multi-Key 路由 + Model Adapter
- `rate_limiter.py` — Token Bucket RPM/TPM 節流
- `streamer.py` — SSE 串流即時轉發
- `cost_guard.py` — M Token 計量 + 每日預算守衛
- `state_machine.py` — 任務狀態機 + Checkpoint 可中斷復原

### 🖥️ Platform Layer (2 平台)

#### Messenger
- `platform/messenger_telegram.py` — Telegram Bot 整合 (polling + 長文分批)

#### Dashboard
- `platform/dashboard/server.py` — aiohttp Web 面板 + SSE 推送
- `platform/dashboard/static/` — 現代深色主題 SPA (Overview / Tasks / SOUL Generator / Settings)

### 🧙 UX Layer
- `onboarding/wizard.py` — 首次啟動互動式引導 (模型選擇 / API Key / SOUL 生成 / Messenger 設定)

### 🔗 Integration
- `main.py` — 一鍵啟動腳本，串接全部模組
- `contracts/interfaces.py` — 全模組介面契約
- `config_schema.py` — config.yaml 驗證 schema + 預設值

### ✅ Testing
- `tests/e2e_test.py` — 端到端測試 (Mock API + Sandbox 檔案生成驗證)

### 📋 Architecture
- 4 核心 + 2 平台，精簡自原始 6+3 架構
- 所有外部感官 (Screen Reader, Browser CDP, Vision) 降級為可選安裝工具
- OS 中立性原則：不禁止任何事情，所有決策權歸 USER
