import asyncio
import logging
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import importlib.util
spec = importlib.util.spec_from_file_location("sandbox_docker", os.path.join(os.path.dirname(__file__), "..", "03_Tool_System", "sandbox_docker.py"))
sandbox_mod = importlib.util.module_from_spec(spec)
valid_spec = spec
if valid_spec and valid_spec.loader:
    valid_spec.loader.exec_module(sandbox_mod)
DockerSandbox = sandbox_mod.DockerSandbox

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

async def run_zero_trust_tests():
    logger.info("============================================================")
    logger.info("🛡️ 開始 Zero Trust 安全攔截機制測試")
    logger.info("============================================================")
    
    sandbox = DockerSandbox()
    
    # 測試 1: 安全指令
    logger.info("\n--- 測試 1: 執行安全指令 (echo) ---")
    safe_code = "print('Hello, safe world!')"
    res1 = await sandbox.execute(code=safe_code, language="python", agent_role="orchestrator")
    logger.info(f"結果: Success={res1.success}, Output={res1.output}, Error={res1.error}")
    assert res1.success is True, "安全指令應該要可以執行"
    
    # 測試 2: 危險指令 (rm -rf /)
    logger.info("\n--- 測試 2: 執行高危險指令 (rm -rf /) ---")
    danger_code = "import os; os.system('rm -rf /')"
    res2 = await sandbox.execute(code=danger_code, language="python", agent_role="orchestrator")
    logger.info(f"結果: Success={res2.success}, Output={res2.output}, Error={res2.error}")
    assert res2.success is False, "危險指令必須被攔截"
    assert "Zero Trust" in res2.error or "Denied" in res2.error, "錯誤訊息必須與 Zero Trust 有關"
    
    # 測試 3: 危險指令 (bash 直接下)
    logger.info("\n--- 測試 3: 執行高危險指令 (bash rm -rf ~) ---")
    danger_bash = "rm -rf ~"
    res3 = await sandbox.execute(code=danger_bash, language="bash", agent_role="orchestrator")
    logger.info(f"結果: Success={res3.success}, Output={res3.output}, Error={res3.error}")
    assert res3.success is False, "Bash 的家目錄刪除必須被攔截"

    logger.info("\n✅ Zero Trust 測試全部通過！安全紅線運作正常。")

if __name__ == "__main__":
    asyncio.run(run_zero_trust_tests())
