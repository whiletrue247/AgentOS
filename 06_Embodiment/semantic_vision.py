"""
06_Embodiment — Semantic Vision (v5.0 SOTA)
=============================================
將螢幕截圖 + 自然語言描述 → 轉換為可操作的 (X, Y) 座標。
使用 Vision LLM (GPT-4o / Claude 3.5 Sonnet / Gemini Pro Vision) 分析截圖。

核心能力：
  1. understand_screen() - 讓 VLM 描述畫面上有什麼
  2. find_element_coordinates() - 給定描述 → 回傳 (X, Y) 座標 (Semantic Click)

支援 Set-of-Marks (SOM) 模式：在截圖上預先標記元素序號供 VLM 選擇。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


class SemanticVision:
    """
    Semantic Vision Engine (v5.0 SOTA)。
    透過 Vision LLM 將「人類語言描述」轉為「螢幕座標」。
    """

    def __init__(self, engine: Any):
        self.engine = engine
        logger.info("👁️ SemanticVision 初始化完成")

    # ----------------------------------------------------------
    # 螢幕理解
    # ----------------------------------------------------------
    async def understand_screen(
        self,
        base64_image: str,
        query: str = "Describe the UI layout and all interactive elements you can see.",
    ) -> str:
        """將截圖送給 Vision LLM，讓它描述畫面內容。"""
        logger.info(f"🖼️ 分析螢幕: '{query[:50]}...'")

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": query},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{base64_image}"},
                    },
                ],
            }
        ]

        try:
            response = await self.engine.gateway.call(
                messages=messages,
                agent_id="vision",
                temperature=0.2,
            )
            result = response["choices"][0]["message"]["content"]
            logger.info(f"👁️ VLM 回覆: {result[:100]}...")
            return result
        except Exception as e:
            logger.error(f"❌ Vision API failed: {e}")
            return f"Vision analysis failed: {e}"

    # ----------------------------------------------------------
    # 元素座標定位 (Semantic Click 核心)
    # ----------------------------------------------------------
    async def find_element_coordinates(
        self,
        base64_image: str,
        description: str,
        screen_width: int = 1920,
        screen_height: int = 1080,
    ) -> Tuple[int, int]:
        """
        核心功能：給定「我想要點擊右上角的紅色結帳按鈕」，
        回傳該按鈕在螢幕上的 (X, Y) 座標。

        使用 CoT (Chain of Thought) 引導 VLM 先描述再定位，提高準確度。
        """
        logger.info(f"🎯 定位元素: '{description}'")

        prompt = f"""Analyze this screenshot carefully.

TASK: Find the UI element matching this description: "{description}"

INSTRUCTIONS:
1. First, describe what you see in the screenshot
2. Identify the element matching the description
3. Estimate its center (X, Y) coordinates

The screen resolution is {screen_width}x{screen_height}.
Return ONLY a JSON object: {{"x": <int>, "y": <int>, "confidence": <float 0-1>, "element_description": "<what you found>"}}
Do NOT include any other text, markdown, or explanation."""

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{base64_image}"},
                    },
                ],
            }
        ]

        try:
            response = await self.engine.gateway.call(
                messages=messages,
                agent_id="vision",
                temperature=0.1,
            )
            raw = response["choices"][0]["message"]["content"]
            coords = self._parse_coordinates(raw)

            if coords:
                x, y = coords
                logger.info(f"✅ 定位成功: ({x}, {y})")
                return x, y

            # Fallback: 回傳螢幕中心
            logger.warning("⚠️ VLM 座標解析失敗，回傳螢幕中心")
            return screen_width // 2, screen_height // 2

        except Exception as e:
            logger.error(f"❌ 座標定位失敗: {e}")
            return screen_width // 2, screen_height // 2

    # ----------------------------------------------------------
    # 批次元素偵測 (SOM-like)
    # ----------------------------------------------------------
    async def detect_all_elements(self, base64_image: str) -> list[dict]:
        """
        偵測截圖中所有可互動的 UI 元素，回傳列表。
        類似 Set-of-Marks (SOM) 但不需要預處理截圖。
        """
        logger.info("🔍 偵測所有可互動元素...")

        prompt = """Analyze this screenshot and list ALL interactive UI elements you can see.
For each element, provide:
- index: sequential number starting from 1
- type: "button", "input", "link", "dropdown", "checkbox", etc.
- label: the visible text or aria-label
- x: estimated center X coordinate
- y: estimated center Y coordinate

Return ONLY a JSON array of objects. No other text."""

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{base64_image}"},
                    },
                ],
            }
        ]

        try:
            response = await self.engine.gateway.call(
                messages=messages,
                agent_id="vision",
                temperature=0.2,
            )
            raw = response["choices"][0]["message"]["content"]
            elements = self._parse_json(raw)
            if isinstance(elements, list):
                logger.info(f"✅ 偵測到 {len(elements)} 個可互動元素")
                return elements
        except Exception as e:
            logger.error(f"❌ 元素偵測失敗: {e}")

        return []

    # ----------------------------------------------------------
    # JSON 解析工具
    # ----------------------------------------------------------
    @staticmethod
    def _parse_coordinates(raw: str) -> Optional[Tuple[int, int]]:
        """從 VLM 回覆中解析 {x, y} 座標。"""
        try:
            # 嘗試清除 markdown code block
            text = raw.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            data = json.loads(text)
            x = int(data.get("x", 0))
            y = int(data.get("y", 0))
            if x > 0 and y > 0:
                return x, y
        except (json.JSONDecodeError, ValueError, KeyError):
            pass
        return None

    @staticmethod
    def _parse_json(raw: str) -> Any:
        """從 VLM 回覆中解析 JSON。"""
        text = raw.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
