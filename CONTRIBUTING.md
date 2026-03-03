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

# 驗證安裝
python -m pytest tests/ -v
```

## 程式碼規範

| 項目 | 工具 | 命令 |
|------|------|------|
| **Lint** | ruff | `ruff check .` |
| **Format** | ruff | `ruff format .` |
| **Type Check** | mypy | `mypy --check-untyped-defs .` |
| **Security** | bandit | `bandit -r . -c pyproject.toml` |
| **Test** | pytest | `pytest tests/ -v --cov` |

- 所有 public API 必須加 **type annotation**
- 每個 class 和 public method 必須有 **docstring**
- PR 必須通過 CI (pytest + bandit + trivy)

## 提交流程

1. Fork 本 repo
2. 建立 feature branch: `git checkout -b feat/your-feature`
3. 確保所有 CI 檢查通過
4. 提交 PR，描述你的改動

## Commit Message 格式

```
<type>: <description>

type = feat | fix | refactor | docs | test | security | ci | chore
```

範例：
```
feat: 新增 ChromaDB 向量記憶 Provider
fix: 修正 sandbox exec_module regex 匹配
security: 強化 Docker sandbox 安全旗標
test: 新增 config validation 單元測試
```

## 模組結構

| 目錄 | 職責 |
|------|------|
| `01_Kernel/` | 靈魂載入器 (SOUL.md) |
| `02_Memory/` | 統一記憶系統 (SQLite + Chroma 向量) |
| `03_Tool_System/` | 工具發現 + 沙盒執行 (Docker / E2B) |
| `04_Engine/` | LLM Gateway + Router + Evolver + Event Trace |
| `05_Orchestrator/` | 多 Agent 編排 (LangGraph + Swarm) |
| `06_Embodiment/` | 桌面自動化 + 瀏覽器控制 + 分級截圖 |
| `07_PKG/` | 個人知識圖譜 (Neo4j / NetworkX) |
| `08_Platform/` | Telegram Bot + Dashboard |
| `contracts/` | 介面定義 + 型別 (SandboxProvider, MemoryProvider 等) |
| `tests/` | 單元測試 + E2E 測試 |

## 安全注意事項

- **絕對不要** 在 PR 中提交 API Key 或密碼
- Sandbox 相關變更必須經過安全審查
- 所有 `exec()`/`eval()` 使用必須有明確的安全理由
- 新增工具必須在 `permissions.yaml` 註冊 ACL 權限
- 高危操作必須附帶 L2 截圖 audit trail

## 暫緩功能

請見 [ROADMAP_DEFERRED.md](./ROADMAP_DEFERRED.md) 了解規劃中但暫緩的功能。
