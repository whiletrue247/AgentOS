import logging
import json
from typing import Any

logger = logging.getLogger(__name__)

class DailyFeedbackLoop:
    """
    負責處理 Agent 每日反饋：
    1. 定期 (如午夜) 讀取前一天的 Audit Trail
    2. 使用 LLM/Critic Agent 評分哪些 Action 成功、哪些失敗
    3. 提煉成 Instruction-Tuning 格式 (Q: Goal, A: CoT + Actions)
    4. 輸出高品質資料，供 auto LoRA 使用。
    """
    
    def __init__(self, engine: Any, audit_provider: Any, export_path: str):
        self.engine = engine
        self.audit_provider = audit_provider
        self.export_path = export_path
        
    async def run_daily_evaluation(self, target_date: str) -> None:
        logger.info(f"🔄 啟動 {target_date} 每日反饋學習與評估 (Daily Feedback Learning)...")
        
        # 1. 抓取當天紀錄 (實戰中從 SQLite 或 JSON log 撈取)
        # logs = self.audit_provider.get_logs_by_date(target_date)
        logs_mock = [
            {"goal": "Download financial report", "success": True, "cot": "I should click download...", "action": {"click": [100, 200]}},
            {"goal": "Login bank", "success": False, "cot": "I should type password...", "action": {"type": "***"}}
        ]
        
        logger.info(f"📊 載入 {len(logs_mock)} 筆互動日誌")
        
        training_samples = []
        
        # 2. 評分與提煉
        for log in logs_mock:
            if log["success"]:
                # 成功的軌跡直接變成正向訓練集
                sample = {
                    "instruction": f"Solve goal: {log['goal']}",
                    "output": f"Thought: {log['cot']}\nAction: {json.dumps(log['action'])}"
                }
                training_samples.append(sample)
            else:
                # 失敗的軌跡呼叫 Gateway 產生 Reflection
                logger.debug(f"🔍 失敗案例反思：{log['goal']}")
                # reflection = await self.engine.gateway.resolve_model(...)
                reflection = "Next time verify element exists before clicking."
                sample = {
                    "instruction": f"Goal: {log['goal']}\nAvoid mistake: {reflection}",
                    "output": f"Thought: I must verify screen state...\nAction: {json.dumps({'wait': 2})}"
                }
                training_samples.append(sample)
                
        # 3. 匯出供 LoRA 使用
        try:
            with open(self.export_path, "w", encoding="utf-8") as f:
                for s in training_samples:
                    f.write(json.dumps(s) + "\n")
            logger.info(f"✅ 成功產出 {len(training_samples)} 筆反饋訓練資料至 {self.export_path}")
        except Exception as e:
            logger.error(f"❌ 產出失敗: {e}")

        # 4. 可選：直接呼叫 LoRATuner 排程器觸發訓練
        # lora_scheduler.trigger_immediate()
