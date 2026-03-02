# 03 ↔ 04 標準派發協議 (Dispatch Protocol)

`03_Tool_Registry` 負責「挑選工具」，`04_Sandbox_Execution` 負責「執行工具」。
兩者之間必須有一份嚴格的資料交接合約，才能確保齒輪完美咬合。

---

## ActionPayload：03 → 04 的「執行指令包」

當 `03_Tool_Registry` 從 API 的 Tool Call 回應中解析出工具請求，並通過 Schema 驗證後，它會將以下標準化的 JSON 封包派發給 `04_Sandbox_Execution`：

```json
{
  "action_id": "uuid4",
  "tool_name": "execute_python",
  "arguments": {
    "code": "print('hello world')",
    "timeout": 30
  },
  "security_level": "sandboxed",
  "sandbox_config": {
    "runtime": "pyodide",
    "network": false,
    "max_memory_mb": 256,
    "timeout_seconds": 60,
    "mount_paths": ["/tmp/workspace"]
  },
  "source": "api_tool_call",
  "timestamp": "2026-03-03T01:45:00Z"
}
```

### 欄位說明

| 欄位 | 類型 | 說明 |
|---|---|---|
| `action_id` | UUID | 本次動作的唯一識別碼，用於日誌追蹤與 Checkpoint |
| `tool_name` | string | 要執行的工具名稱 (需已註冊於 Registry) |
| `arguments` | object | API 傳入的參數 (已通過 Schema 驗證) |
| `security_level` | enum | `trusted` (直接執行) / `sandboxed` (隔離執行) / `cloud` (外包 E2B) |
| `sandbox_config` | object | 沙盒的隔離參數：runtime 選擇、網路權限、記憶體上限、超時秒數 |
| `source` | string | 這個請求的觸發來源（API tool_call / cron / heartbeat） |
| `timestamp` | ISO8601 | 派發時間 |

---

## ExecutionResult：04 → 05 Engine 的「執行結果包」

`04_Sandbox_Execution` 執行完畢後，無論成功或失敗，都會回傳以下標準化的結果封包。
這份結果會被 `05_24_7_Engine` 接收，塞入 API 的對話歷史，推進下一輪 ReAct 循環。

```json
{
  "action_id": "uuid4（與 ActionPayload 相同）",
  "exit_code": 0,
  "stdout": "hello world\n",
  "stderr": "",
  "truncated": false,
  "truncation_info": null,
  "execution_time_ms": 45,
  "sandbox_used": "pyodide",
  "timestamp": "2026-03-03T01:45:01Z"
}
```

### 欄位說明

| 欄位 | 類型 | 說明 |
|---|---|---|
| `action_id` | UUID | 與對應的 ActionPayload 一致，用於關聯追蹤 |
| `exit_code` | int | 0 = 成功，非 0 = 失敗，-1 = 被 Watchdog 超時斬殺 |
| `stdout` | string | 標準輸出 (已經過 Head-Tail Truncator 截斷處理) |
| `stderr` | string | 標準錯誤輸出 |
| `truncated` | bool | 是否被截斷器處理過 |
| `truncation_info` | object/null | 若被截斷：`{"original_length": 47000, "kept_head": 1000, "kept_tail": 2000}` |
| `execution_time_ms` | int | 實際執行耗時 (毫秒) |
| `sandbox_used` | string | 實際使用的沙盒引擎 (pyodide / e2b / chroot / native) |
| `timestamp` | ISO8601 | 執行完成時間 |

### 特殊狀態處理

| exit_code | 含義 | Engine 行為 |
|---|---|---|
| `0` | 成功 | 將 stdout 塞回對話歷史，推進下一輪 |
| `1` | 工具邏輯錯誤 | 將 stderr 塞回歷史，讓 AI 自我修正 |
| `-1` | Timeout 被 Kill | 附加系統警告訊息，讓 AI 知道超時原因 |
| `-2` | 記憶體超限 (OOM) | 建議 AI 減小輸入資料量或改用雲端沙盒 |
