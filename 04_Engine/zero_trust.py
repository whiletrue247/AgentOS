import yaml
import re
import os
import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)

class PermissionDeniedError(Exception):
    """當 Agent 的操作被 Zero Trust 攔截時拋出"""

class ZeroTrustInterceptor:
    """
    零信任核心引擎，用於在 Sandbox 或 Tool System 執行真正動作前，
    攔截並檢查能力 (Capabilities) 與意圖 (Intent)。
    """
    def __init__(self, config_path: str = "config/permissions.yaml"):
        self.config = self._load_config(config_path)
        self.regexes = [re.compile(pattern) for pattern in self.config.get("policies", {}).get("destructive_commands_regex", [])]
        logger.info(f"🛡️ ZeroTrust 初始化完成，載入了 {len(self.regexes)} 條高危險紅線指令正規表示式")

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        full_path = os.path.join(os.getcwd(), config_path)
        if not os.path.exists(full_path):
            logger.warning(f"⚠️ Permissions 設定檔 {full_path} 不存在，全部套用預設高維安隔離。")
            return {"roles": {}, "policies": {"destructive_commands_regex": [r"rm\s+-rf\s+/"]}}
        
        with open(full_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def verify_action(self, role: str, action_type: str, payload: str) -> Tuple[bool, str]:
        """
        驗證 Agent 的特定行為
        role: "orchestrator", "coder", etc.
        action_type: "shell", "file", "network"
        payload: 要執行的具體指令或路徑
        
        回傳: (is_allowed, reason)
        """
        role_config = self.config.get("roles", {}).get(role, self.config.get("roles", {}).get("default", {}))
        
        # 1. Broad Capability Check
        if action_type == "shell" and not role_config.get("can_execute_shell", False):
            return False, f"Role '{role}' is missing 'can_execute_shell' capability."
        
        if action_type == "network" and not role_config.get("can_access_network", False):
            return False, f"Role '{role}' is missing 'can_access_network' capability."

        # 2. Content Deep Inspection (特別是 Shell)
        if action_type == "shell":
            for regex in self.regexes:
                if regex.search(payload):
                    logger.critical(f"🚨 [ZERO TRUST] 攔截危險操作！角色: {role}, 指令: {payload}")
                    
                    # 假裝這裡有 Telegram 通知 (即時通知)
                    self._notify_human_supervisor(role, payload)
                    
                    # 啟動軟回滾訊號
                    return False, "Execution Denied by Human Supervisor. Destructive action not allowed. Soft-Rollback triggered."
            
        return True, "Passed"

    def _notify_human_supervisor(self, role: str, payload: str):
        """假想的外部通知服務 (Telegram / Dashboard)"""
        logger.info(f"🔔 [通知] 傳送警告至主管 Dashboard: Agent ({role}) 試圖執行 {payload}")

# 單例模式供全域調用
_interceptor_instance = None
def get_interceptor():
    global _interceptor_instance
    if not _interceptor_instance:
         _interceptor_instance = ZeroTrustInterceptor()
    return _interceptor_instance
