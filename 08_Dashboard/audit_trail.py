import json
import logging
import os
import datetime
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class AuditTrail:
    """
    可視化追蹤與稽核日誌。
    紀錄每一步 CoT (Thought, Action, Observation, Environment Image),
    提供給 Dashboard 或人力審查使用。
    """
    def __init__(self, log_dir: str = "logs/audit"):
        self.log_dir = os.path.join(os.getcwd(), log_dir)
        os.makedirs(self.log_dir, exist_ok=True)
        self.session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(self.log_dir, f"session_{self.session_id}.jsonl")
        logger.info(f"🕵️ AuditTrail 初始化，寫入檔: {self.log_file}")

    def log_step(
        self, 
        role: str,
        step_index: int, 
        thought: str, 
        action: Dict[str, Any], 
        observation: str, 
        screenshot_path: str = None
    ):
        """記錄單一 CoT 節點"""
        record = {
            "timestamp": datetime.datetime.now().isoformat(),
            "role": role,
            "step": step_index,
            "chain_of_thought": thought,
            "action": action,
            "observation": observation[:500] if observation else None, # 截斷過長觀測
            "screenshot": screenshot_path
        }
        
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            
        logger.info(f"📝 記錄 Visual CoT (Step {step_index}, Role: {role}) 完畢。")

    def get_recent_trail(self, limit: int = 20) -> List[Dict[str, Any]]:
        """給前端 Dashboard 讀取的即時軌跡"""
        if not os.path.exists(self.log_file):
            return []
            
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                # 回傳最後 limit 筆
                return [json.loads(line) for line in lines[-limit:]]
        except Exception as e:
            logger.error(f"❌ 無法讀取 Audit Trail: {e}")
            return []
