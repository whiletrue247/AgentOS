# Contributing to AgentOS

感謝你考慮為 AgentOS 做出貢獻！以下是參與方式。

## 開發環境設定

```bash
# Clone
git clone https://github.com/whiletrue247/AgentOS.git
cd AgentOS

# 安裝全部依賴 (推薦 uv)
uv pip install -e ".[all]"

# 或用 pip
pip install -e ".[dev]"
```

## 程式碼規範

- **Linting**: `pyflakes .` 零警告
- **測試**: `pytest tests/ -v` 全通過
- **Type hints**: 所有 public API 必須加 type annotation
- **Docstring**: 每個 class 和 public method 必須有 docstring

## 提交流程

1. Fork 本 repo
2. 建立 feature branch: `git checkout -b feat/your-feature`
3. 確保 `pyflakes .` 和 `pytest` 通過
4. 提交 PR，描述你的改動

## 模組結構

| 目錄 | 職責 |
|------|------|
| `01_Kernel/` | 靈魂載入器 (SOUL.md) |
| `02_Memory*/` | 統一記憶系統 |
| `03_Tool_System/` | 工具發現 + 沙盒執行 |
| `04_Engine/` | LLM Gateway + Router + 狀態機 |
| `05_Orchestrator/` | 多 Agent 編排 (LangGraph) |
| `06_Embodiment/` | 桌面自動化 + 瀏覽器控制 |
| `07_PKG/` | 個人知識圖譜 (Neo4j/NetworkX) |
| `08_Dashboard/` | CLI 面板 + 審計追蹤 |
| `09_OS_Integration/` | 跨平台 OS Hook |
| `10_Marketplace/` | 工具/靈魂市集 |
| `11_Sync_Handoff/` | 跨裝置同步 |

## 安全注意事項

- **絕對不要** 在 PR 中提交 API Key 或密碼
- Sandbox 相關變更必須經過安全審查
- 所有 `exec()`/`eval()` 使用必須有明確的安全理由
