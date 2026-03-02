import json
import logging
import base64
from typing import Optional, Dict, Any
import uuid

logger = logging.getLogger(__name__)

class HandoffManager:
    """ 
    跨裝置 Agent 狀態接力管理器
    允許使用者在手機上的 Agent 執行到一半時，把任務丟回電腦版 Agent 繼續執行。
    反之亦然。透過序列化 StateMachine 的狀態，並透過 QR Code / Cloud Relay 交換。
    """
    
    def __init__(self, relay_server_url: str = "wss://relay.agentos.local"):
        self.relay_server_url = relay_server_url
        self.local_device_id = str(uuid.uuid4())[:12]
        logger.info(f"📱 Handoff Manager initialized (Device: {self.local_device_id})")
        
    def export_session_state(self, current_task_id: str, state_machine_data: Dict[str, Any]) -> str:
        """ 將當前任務狀態打包加密，準備交接 """
        payload = {
            "version": "1.0",
            "source_device": self.local_device_id,
            "task_id": current_task_id,
            "state_snapshot": state_machine_data,
            "m_token_balance_proof": "cryptographic_proof_xyz"
        }
        
        # 轉成 base64 模擬加密/序列化
        json_str = json.dumps(payload)
        base64_payload = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")
        
        handoff_uri = f"agentos://handoff?payload={base64_payload}"
        logger.info(f"🔄 產生 Handoff URI 成功。長度: {len(handoff_uri)} bytes")
        # 實戰中，這裡會調用 qrcode 庫將 handoff_uri 畫成 QR Code 供手機掃描
        return handoff_uri
        
    def import_session_state(self, handoff_uri: str) -> Optional[Dict[str, Any]]:
        """ 接收來自其他裝置的接力 URI，解密並還原為狀態字典 """
        try:
            if not handoff_uri.startswith("agentos://handoff?payload="):
                logger.error("❌ 無效的 Handoff URI 格式")
                return None
                
            base64_payload = handoff_uri.split("payload=")[1]
            json_str = base64.b64decode(base64_payload).decode("utf-8")
            payload = json.loads(json_str)
            
            source_device = payload.get("source_device", "Unknown")
            task_id = payload.get("task_id", "Unknown")
            state = payload.get("state_snapshot", {})
            
            logger.info(f"✅ 成功接力！來自裝置 {source_device} 的任務 {task_id}")
            logger.info(f"📜 恢復上下文訊息數量: {len(state.get('messages', []))} 條紀錄")
            
            # 實戰中這裡會把 state 餵給本地的 StateMachine
            return state
            
        except Exception as e:
            logger.error(f"❌ 狀態接力還原失敗: {e}")
            return None
