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
            self._log_audit(role, action_type, payload, "blocked", "medium", "Missing 'can_execute_shell'")
            return False, f"Role '{role}' is missing 'can_execute_shell' capability."
        
        if action_type == "network" and not role_config.get("can_access_network", False):
            self._log_audit(role, action_type, payload, "blocked", "medium", "Missing 'can_access_network'")
            return False, f"Role '{role}' is missing 'can_access_network' capability."

        # 2. Content Deep Inspection (特別是 Shell)
        if action_type == "shell":
            for regex in self.regexes:
                if regex.search(payload):
                    logger.critical(f"🚨 [ZERO TRUST] 攔截危險操作！角色: {role}, 指令: {payload}")
                    
                    self._log_audit(role, action_type, payload, "blocked", "critical", f"Regex match: {regex.pattern}")
                    
                    # 取出使用者決策
                    decision = self._notify_human_supervisor(role, payload)
                    
                    if decision == 'execute':
                        logger.warning("🧑‍⚖️ Human override: Allowing destructive command execution.")
                        self._log_audit(role, action_type, payload, "human_override", "critical", "Explicitly allowed by human")
                        return True, "Passed via Human Override"
                    
                    elif decision == 'modify':
                        print("請輸入修改後的新指令 (如果為空則視同取消):")
                        try:
                            # 由於 input() 攔截，若無 tty 已經會在 notify 擋下來了
                            new_payload = input("New Command > ").strip()
                            if new_payload:
                                logger.info(f"🧑‍⚖️ Human override: Modifying payload to: {new_payload}")
                                self._log_audit(role, action_type, f"Modified from: {payload} TO: {new_payload}", "human_modified", "high", "Payload modified by human")
                                # 通知 caller 使用新 payload
                                return True, f"MODIFIED:{new_payload}"
                        except (EOFError, KeyboardInterrupt):
                            pass
                            
                    # 取消或修改為空
                    return False, "Execution Denied by Human Supervisor. Soft-Rollback triggered."
            
        return True, "Passed"

    def _log_audit(self, role: str, action_type: str, payload: str, result: str, risk: str, reason: str):
        try:
            from audit_trail import get_audit_trail
            get_audit_trail().log_action(
                agent_id=role,
                action_type=f"zt_{action_type}",
                payload=f"{reason} | {payload}",
                result_status=result,
                risk_level=risk
            )
        except ImportError:
            pass

    def _notify_human_supervisor(self, role: str, payload: str) -> str:
        """
        通知主管並要求決策 (Human-in-the-Loop)。
        實戰中這裡可能串接 Telegram Bot 或 WebSocket UI。
        回傳: 'execute', 'modify', 或 'cancel'
        """
        logger.info(f"🔔 [通知] 傳送警告至主管 Dashboard: Agent ({role}) 試圖執行高危操作")
        print("\n\033[93m" + "="*60)
        print("🚨 [Zero Trust Alert] 偵測到高危操作！")
        print(f"Agent Role : {role}")
        print(f"Payload    :\n{payload}")
        print("="*60 + "\033[0m")
        
        # 為了能在 CI/測試中自動通過，若無 TTY 直接阻擋
        import sys
        if not sys.stdin.isatty():
            logger.warning("No TTY available. Auto-canceling dangerous operation.")
            return 'cancel'
            
        print("請選擇你要進行的操作:")
        print("  [e] 執行 (Execute)")
        print("  [m] 修改指令 (Modify)")
        print("  [c] 取消/回滾 (Cancel)")
        
        while True:
            choice = input("您的選擇 [e/m/c]? ").strip().lower()
            if choice == 'e':
                return 'execute'
            elif choice == 'm':
                return 'modify'
            elif choice == 'c':
                return 'cancel'
            else:
                print("無效的選擇，請輸入 e, m, 或 c。")

# 單例模式供全域調用
_interceptor_instance = None
def get_interceptor():
    global _interceptor_instance
    if not _interceptor_instance:
         _interceptor_instance = ZeroTrustInterceptor()
    return _interceptor_instance
