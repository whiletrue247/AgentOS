# 開源貢獻指南 (Contributing Guide)

感謝你對 AgentOS 專案有興趣！我們非常歡迎社群的參與，無論是修復 Bug、新增工具外掛 (Tools) 或是強化架構，你的貢獻都將幫助 AgentOS 變得更強大。

## 🚀 開發環境設定

### 1. 取得程式碼與安裝相依套件
官方推薦使用 \`uv\` 或標準的 \`pip\` 來建立隔離的虛擬環境：

```bash
git clone https://github.com/whiletrue247/AgentOS.git
cd AgentOS
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# 或者使用 uv: uv pip install -r requirements.txt
```

### 2. 啟動與測試
AgentOS 有很完整的端到端測試，可以確保你的修改不會破壞核心鏈路。
```bash
# 執行 E2E 測試 (自動以 Mock 模式運行，不需要消耗真實 API Token)
python tests/e2e_test.py
```

## 🛠️ 如何貢獻新工具 (Tools)

AgentOS 的 Tool System 設計非常容易擴充。如果你想要新增一個工具 (例如: 發推特、串接 Notion、操作瀏覽器)，請遵循以下步驟：

1. 在 \`03_Tool_System/plugins/\` 目錄下建立你的 Python 腳本 (例如 \`notion_writer.py\`)。
2. 確保腳本內包含標準的 \`TOOL_SCHEMA\` 字典：
   ```python
   # 範例
   TOOL_SCHEMA = {
       "name": "notion_writer",
       "description": "Writes content to Notion.",
       "parameters": {
           "type": "object",
           "properties": {
               "content": {"type": "string", "description": "The content to write"}
           },
           "required": ["content"]
       },
       "requires_network": True
   }
   
   def execute(content: str) -> str:
       # 實作邏輯...
       return "Success"
   ```
3. 發起 Pull Request，並在說明中附上該工具的測試截圖。

## 🛡️ 安全性相關備註 (Security Notice)

AgentOS 非常重視執行 LLM 代碼的安全性：
* 所有外部下載的外掛都會經過 **AST 靜態語法樹掃描**，避免 RCE。
* **DockerSandbox** 是官方唯一認可的生產環境隔離方案。如果你修改了 \`SubprocessSandbox\` 的行為，請務必先執行 \`python tests/test_sandbox_security.py\` 確保 \`resource\` (CPU/RAM) 限制機制沒有被破壞。

## 📝 提交 Pull Request (PR)

1. 請務必分支出一個新的 branch (例如 \`feat/add-notion-tool\`).
2. 提交風格請參考 Conventional Commits (例如 \`feat:\`, \`fix:\`, \`docs:\`)。
3. 我們的 GitHub Actions 會自動執行架構與依賴套件掃描 (\`bandit\` & \`trivy\`)，確保你的 PR 右方有出現綠色勾勾 (Checks Passed)。
