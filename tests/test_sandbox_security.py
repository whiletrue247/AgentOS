import asyncio
import os
import sys
import importlib

# 把上層目錄加入 sys.path, 讓測試跑在專案根目錄時能找到模組
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from contracts.interfaces import ToolCallResult
from typing import Protocol

class SandboxTest(Protocol):
    async def execute(self, code: str, language: str = "python", timeout_seconds: int = 60, network_allowed: bool = False) -> ToolCallResult: ...

async def run_security_tests():
    # 動態載入 Sandbox (優先測試 SubprocessSandbox 的資源限制)
    sandbox_module = importlib.import_module('03_Tool_System.sandbox_subprocess')
    SubprocessSandbox = sandbox_module.SubprocessSandbox
    sandbox = SubprocessSandbox()

    print("==========================================")
    print("🛡️  開始 AgentOS 安全性盲測 (Security Tests)")
    print("==========================================")

    # ----------------------------------------------------
    # Case 1: CPU Bomb (無窮迴圈)
    # ----------------------------------------------------
    print("\\n[Test 1] CPU Bomb (Infinite Loop)")
    cpu_bomb_code = '''
import time
print("Starting CPU Bomb...")
while True:
    pass
'''
    
    print("發射 Payload: while True: pass")
    # SubprocessSandbox 在預設情況下，resource limit 設為 10 秒。
    # Timeout_seconds 我們給 15 秒，看哪個先觸發 (理論上 RLIMIT 會送 SIGKILL 導致 returncode < 0)
    result = await sandbox.execute(cpu_bomb_code, timeout_seconds=15)
    
    print(f"執行結果: Success={result.success}")
    if not result.success:
         print(f"✅ 成功防堵 CPU 炸彈！錯誤訊息: {result.error}")
    else:
         print("❌ 警告: CPU 炸彈未被防堵，仍回傳了 Success=True")


    # ----------------------------------------------------
    # Case 2: RAM Bomb (記憶體耗盡)
    # ----------------------------------------------------
    print("\\n[Test 2] RAM Bomb (Memory Exhaustion)")
    # 嘗試分配大約 1GB (1024 * 1024 * 1024 字元)，SubprocessSandbox 應該限制在 256MB
    ram_bomb_code = '''
print("Starting RAM Bomb...")
large_list = []
try:
    for i in range(100):
        large_list.append("A" * 10 * 1024 * 1024) # 每次吃 10MB
        print(f"Allocated {i * 10} MB")
except MemoryError:
    print("Caught MemoryError internally!")
'''
    
    print("發射 Payload: 分配過多記憶體")
    result = await sandbox.execute(ram_bomb_code, timeout_seconds=15)
    
    print(f"執行結果: Success={result.success}")
    if not result.success or "MemoryError" in result.output or "MemoryError" in str(result.error) or "Killed" in str(result.error):
         print("✅ 成功防堵 RAM 炸彈！")
         if result.error:
             print(f"錯誤訊息: {result.error}")
         if result.output:
             print(f"部分輸出:\\n{result.output}")
    else:
         print(f"❌ 警告: RAM 炸彈未被阻擋。Output: {result.output}")

    print("\\n==========================================")
    print("🏁 安全性測試完成")
    print("==========================================")
    
    await sandbox.cleanup()

if __name__ == "__main__":
    asyncio.run(run_security_tests())
