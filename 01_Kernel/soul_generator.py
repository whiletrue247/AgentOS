"""
01_Kernel — SOUL Generator
===========================
協助使用者快速生成高品質的 SOUL.md (系統提示詞)。
接收簡單的人類輸入 (例如："我要一個能幫我抓取網頁資料並整理成 Markdown 的助理")，
透過 LLM 擴寫成 AgentOS 標準的 SOUL 格式 (包含 Identity, Objective, Rules 等)。

支援直接使用 Engine 來發送擴寫請求。
"""

import logging
from pathlib import Path

from config_schema import AgentOSConfig
from paths import get_soul_path

logger = logging.getLogger(__name__)


class SoulGenerator:
    """自動產生 SOUL.md 的工具"""
    
    def __init__(self, config: AgentOSConfig, engine=None):
        self.config = config
        self.engine = engine  # Needs engine to call LLM for generation
        
        # 內建一個專門產生 SOUL 的超級提示詞
        self._meta_prompt = """
You are an expert Prompt Engineer and System Architect for AgentOS.
Your task is to take a user's brief description of what they want an AI agent to do, 
and expand it into a comprehensive, professional `SOUL.md` file.

The `SOUL.md` format MUST follow this exact Markdown structure:

```markdown
# [Agent Name]
[1-2 sentences summarizing the identity]

## 🎯 核心目標 (Core Objectives)
- [Objective 1]
- [Objective 2]

## 📜 行為準則 (Rules & Guidelines)
- [Rule 1: e.g., tone, formatting, strict limitations]
- [Rule 2]

## 🛠️ 預設技能 (Default Skills)
- [Skill/Tool 1 that the agent should definitely be aware of and use]
- [Skill/Tool 2]
```

User's description of their desired Agent:
{user_input}

Output ONLY the markdown content for the SOUL.md file, starting with the `# [Agent Name]`. Do not include any other conversational filler.
"""

    async def generate(self, user_description: str, save_path: Optional[str] = None) -> str:
        """
        利用 LLM (透過 Gateway) 一鍵生成 SOUL.md。
        """
        save_path = save_path or str(get_soul_path())
        if not self.engine:
            raise ValueError("SoulGenerator requires an initialized Engine to work.")
            
        logger.info(f"🧠 開始生成 SOUL.md，基於使用者描述: {user_description[:30]}...")
        
        prompt = self._meta_prompt.format(user_input=user_description)
        
        # 我們創立一個臨時的對話來獲得結果
        try:
            # Override SOUL temporarily to let the engine act purely as the meta-prompt engineer
            # We can do this by passing a clean conversation history
            messages = [{"role": "system", "content": "You are a specialized System Prompt Engineer."}]
            
            soul_content = await self.engine.handle_message(
                user_message=prompt, 
                agent_id="soul_generator", # 獨立的 agent ID，不混淆 default 記憶
                conversation_history=messages
            )
            
            # 簡單清理 (去掉可能被 LLM 包裝的 markdown tag)
            soul_content = soul_content.strip()
            if soul_content.startswith("```markdown"):
                soul_content = soul_content[11:]
            if soul_content.endswith("```"):
                soul_content = soul_content[:-3]
            soul_content = soul_content.strip()
            
            # 存檔
            output_path = Path(save_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(soul_content, encoding="utf-8")
            
            logger.info(f"✅ 生成成功！已儲存至 {save_path}")
            return soul_content
            
        except Exception as e:
            logger.error(f"❌ SOUL Generator 發生錯誤: {e}")
            raise
