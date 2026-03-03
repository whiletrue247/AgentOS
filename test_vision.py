import asyncio
import logging
import sys
import os

from config_schema import AgentOSConfig
from importlib import import_module
engine_mod = import_module('04_Engine.engine')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VISION_TEST")

class MockGateway:
    def __init__(self):
        self.step = 0
        
    async def call(self, messages, agent_id, **kwargs):
        self.step += 1
        print(f"[MockGateway] Step {self.step} called with {len(messages)} messages.")
        
        # 第一次呼叫，我們假裝 LLM 決定呼叫截圖工具
        if self.step == 1:
            return {
                "choices": [{
                    "message": {
                        "content": "Let me take a look at your screen.",
                        "tool_calls": [{
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "SYS_TAKE_SCREENSHOT",
                                "arguments": "{}"
                            }
                        }]
                    }
                }]
            }
        
        # 第二次呼叫，我們檢查 message 裡面是不是真的有收到圖片資料
        elif self.step == 2:
            last_msg = messages[-1]
            if isinstance(last_msg["content"], list):
                has_image = any(part.get("type", "") == "image_url" for part in last_msg["content"])
                if has_image:
                    return {
                        "choices": [{
                            "message": {
                                "content": "I see a screenshot encoded in base64. The process works perfectly!"
                            }
                        }]
                    }
            
            return {
                "choices": [{
                    "message": {
                        "content": "I did NOT receive an image. Something is wrong."
                    }
                }]
            }

async def test_vision():
    config = AgentOSConfig()
    engine = engine_mod.Engine(config)
    engine.inject(gateway=MockGateway())
    
    print("🚀 發送測試指令：幫我截取螢幕並閱讀畫面")
    
    try:
        final_answer = await engine.handle_message("截圖吧")
        print(f"\n✅ 最終回應:\n{final_answer}")
    except Exception as e:
        print(f"\n❌ 測試失敗: {e}")

if __name__ == "__main__":
    asyncio.run(test_vision())
