"""
e2e_test.py
===========
AgentOS 端到端測試 (End-to-End Test)。
驗證 OS 的四大核心 (Kernel, Memory, ToolSystem, Engine) 是否能協同工作。

預期行為：
1. 載入假 SOUL
2. 初始化 Sandbox 和 Tools
3. 給予指令：「寫一個 Python 腳本來計算費氏數列(fibonacci)並儲存為 test_fib.py」
4. 確認檔案是否成功被工具創建
"""

import asyncio
import os
import sys
from pathlib import Path
from importlib import import_module

# 把專案根目錄加回 sys.path，以便 import 各路徑模組
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config_schema import load_config
from contracts.interfaces import ToolCallResult
from paths import get_data_dir

async def run_e2e_test():
    print("="*60)
    print("🚀 開始 AgentOS E2E 本地測試 (不含 Telegram)")
    print("="*60)

    # 1. Config & Kernel
    config = load_config()
    
    # 檢查是否設定了 API Key，這在真實環境 E2E 中是必須的
    has_api_key = any(p.api_key for p in config.gateway.providers) or any(p.base_url for p in config.gateway.providers)
    if not has_api_key:
        print("⚠️ 警告：找不到 config.yaml 內的 API Key。")
        print("    請先執行 `python main.py` 來啟動首頁精靈填寫 API Key。")
        print("    本次測試將使用這是一個 Mock API 直接假裝成功回覆，不呼叫外部網路。")
        # 直接賦予一個假的 token 以防檢查報錯，下面在攔截 Gateway call
        config.gateway.providers[0].api_key = "mock_key_for_test"

    # 關閉串流避免畫面太亂
    config.engine.streaming = True
    config.budget.daily_limit_m = 10.0
    
    # 載入 01_Kernel
    kernel_mod = import_module("01_Kernel.kernel")
    Kernel = kernel_mod.Kernel
    
    # mock soul
    soul_content = """# E2E Test Agent
A highly capable test agent.
## 📜 Rules
You must complete the user's task absolutely without asking for human confirmation.
Whenever you are asked to write code, just use writing tools.
"""

    # 2. Memory (SQLite)
    memory_mod = import_module("02_Memory.memory_manager")
    sqlite_mod = import_module("02_Memory.providers.sqlite")
    # 準備測試用的隔離資料夾與檔案
    data_dir = get_data_dir()
    test_db = str(data_dir / "test_memory.db")
    if os.path.exists(test_db):
        os.remove(test_db)
    sqlite_provider = sqlite_mod.SQLiteMemoryProvider(db_path=test_db)
    memory_manager = memory_mod.MemoryManager(provider=sqlite_provider)

    # 3. Tool System
    catalog_mod = import_module("03_Tool_System.catalog")
    sys_tools_mod = import_module("03_Tool_System.sys_tools")
    sandbox_module = import_module("03_Tool_System.sandbox")
    subprocess_mod = import_module("03_Tool_System.sandbox_subprocess")
    docker_mod = import_module("03_Tool_System.sandbox_docker")
    truncator_mod = import_module("03_Tool_System.truncator")
    
    cat_path = str(data_dir / "test_catalog.json")
    tool_catalog = catalog_mod.ToolCatalog(config=config, catalog_path=cat_path)
    sys_tools_mod.register_system_tools(tool_catalog)
    
    # 偵測 Docker
    import subprocess
    has_docker = False
    try:
        subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        has_docker = True
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
        
    if has_docker:
        print("🐳 檢測到 Docker，啟用強隔離 DockerSandbox 進行測試")
        sandbox_provider = docker_mod.DockerSandbox(work_dir=".")
    else:
        print("⚠️ 找不到 Docker，降級使用零隔離 SubprocessSandbox 進行測試")
        sandbox_provider = subprocess_mod.SubprocessSandbox(work_dir=".")
        
    sandbox_manager = sandbox_module.SandboxManager(config=config, provider=sandbox_provider)
    truncator = truncator_mod.Truncator(config=config)

    # 4. Engine
    engine_mod = import_module("04_Engine.engine")
    gateway_mod = import_module("04_Engine.gateway")
    rate_mod = import_module("04_Engine.rate_limiter")
    cost_mod = import_module("04_Engine.cost_guard")
    state_mod = import_module("04_Engine.state_machine") # Added import for state_machine
    
    gateway = gateway_mod.APIGateway(config)
    rate_limiter = rate_mod.RateLimiter(rpm=60, tpm=200000) # --- 守衛 / 狀態機 ---
    cost_guard = cost_mod.CostGuard(config, history_path=str(data_dir / "test_cost.json"))
    state_machine = state_mod.StateMachine(checkpoint_dir=str(data_dir / "test_checkpoints"))
    
    engine = engine_mod.Engine(config)
    
    if not has_api_key:
        import json
        mock_state = {"called": False}
        async def mock_call(*args, **kwargs):
            if not mock_state["called"]:
                mock_state["called"] = True
                
                cmd = "cat << 'EOF' > test_fib.py\ndef fib(n):\n    if n <= 1: return n\n    return fib(n-1) + fib(n-2)\n\nfor i in range(1, 11):\n    print(fib(i))\nEOF"
                args_str = json.dumps({"command": cmd, "timeout": 10})
                
                return {
                    "choices": [{
                        "message": {
                            "content": "",
                            "role": "assistant",
                            "tool_calls": [{
                                "id": "call_abc123",
                                "type": "function",
                                "function": {
                                    "name": "SYS_TOOL_EXECUTE",
                                    "arguments": args_str
                                }
                            }]
                        },
                        "finish_reason": "tool_calls"
                    }],
                    "usage": {"total_tokens": 50}
                }
            else:
                return {
                    "choices": [{
                        "message": {
                            "content": "我已經幫您計算完成並寫入 test_fib.py 檔案了。",
                            "role": "assistant"
                        },
                        "finish_reason": "stop"
                    }],
                    "usage": {"total_tokens": 100}
                }
        gateway.call = mock_call

    async def tool_executor(req):
        if req.tool_name != "SYS_TOOL_EXECUTE":
            tool_schema = tool_catalog.get_tool(req.tool_name)
            if not tool_schema:
                return ToolCallResult(tool_name=req.tool_name, success=False, output="", error=f"Tool '{req.tool_name}' not found")
                
        try:
            import json
            args_dict = json.loads(req.arguments) if isinstance(req.arguments, str) else req.arguments
            cmd = args_dict.get("command", "")
            
            if req.tool_name == "SYS_TOOL_EXECUTE":
                # 直接轉成 bash script 給 Sandbox 執行
                print(f"🔧 Sandbox 執行指令: {cmd}")
                result = await sandbox_manager.execute(code=cmd, language="bash", timeout_seconds=10)
                print(f"🔧 Sandbox 執行結果: success={result.success}, output={result.output}, error={result.error}")
            else:
                # 預設行為
                result = await sandbox_manager.execute(code=req.arguments, language="python")
                
            out = truncator.truncate(result.output) if result.output else ""
            return ToolCallResult(tool_name=req.tool_name, success=result.success, output=out, error=result.error)
        except Exception as e:
            return ToolCallResult(tool_name=req.tool_name, success=False, output="", error=str(e))

    engine.inject(
        gateway=gateway,
        rate_limiter=rate_limiter,
        tool_executor=tool_executor,
        memory_manager=memory_manager,
        soul_content=soul_content
    )

    # 5. 發送測試指令
    target_file = "test_fib.py"
    if os.path.exists(target_file):
        os.remove(target_file)
        
    prompt = f"請寫一個 Python 腳本計算費氏數列第一到第十項，並將程式碼透過 SYS_TOOL_EXECUTE 寫入 '{target_file}' 中(使用 bash 指令 cat 寫入)，成功之後回覆我完成。"
    
    print(f"\n💬 發送 Prompt: {prompt}")
    print("-" * 60)
    
    reply = await engine.handle_message(
        user_message=prompt,
        agent_id="e2e_tester",
    )
    
    print("-" * 60)
    print(f"🤖 Agent 回覆: {reply}")
    
    # 6. 驗證結果
    if os.path.exists(target_file):
        print(f"✅ 成功找到創建的檔案: {target_file}")
        with open(target_file, "r") as f:
            code = f.read()
            print("檔案內容預覽:")
            print("```python")
            print(code[:200])
            print("```")
        os.remove(target_file)  # 清理
    else:
        print(f"❌ 找不到預期創建的檔案: {target_file}")
        sys.exit(1)
        
    # 清理資料庫
    if os.path.exists(test_db):
        os.remove(test_db)
        
    print("\n🎉 E2E 測試順利完成！全平台核心對接正常。")


if __name__ == "__main__":
    asyncio.run(run_e2e_test())
