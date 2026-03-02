import asyncio
import logging
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../06_Embodiment'))

from desktop_runtime import DesktopRuntime
from browser_cdp import BrowserCDP
from semantic_vision import SemanticVision

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

async def run_embodiment_test():
    logger.info("============================================================")
    logger.info("👁️ 開始電腦實體操作 (Computer Use) 基礎模組測試")
    logger.info("============================================================")
    
    # 測試 DesktopRuntime
    try:
        desktop = DesktopRuntime()
        logger.info(f"📍 當前視窗: {desktop.get_active_window_info()}")
        screenshot_data = desktop.take_screenshot()
        logger.info("✅ DesktopRuntime 截圖 API 測試通過")
    except Exception as e:
        logger.error(f"❌ DesktopRuntime 測試失敗: {e}")
        
    # 測試 SemanticVision
    try:
        class MockEngine:
            pass
        vision = SemanticVision(MockEngine())
        
        # 1. 解讀畫面
        desc = await vision.understand_screen(screenshot_data, "Where is the login button?")
        logger.info(f"📍 Vision 模型解讀: {desc}")
        
        # 2. 獲取座標
        x, y = await vision.find_element_coordinates(screenshot_data, "Green submit button")
        logger.info(f"✅ SemanticVision 座標計算: ({x}, {y})")
        
        # 3. 再透過 Desktop 點擊
        desktop.click(x, y)
        logger.info("✅ DesktopRuntime 接收座標點擊測試通過")
    except Exception as e:
        logger.error(f"❌ SemanticVision 測試失敗: {e}")
        
    # 測試 Browser CDP
    try:
        browser = BrowserCDP(headless=True)
        await browser.navigate("https://news.ycombinator.com")
        dom = await browser.get_dom_snapshot()
        logger.info(f"📍 獲取 DOM 摘要: {dom[:50]}...")
        result = await browser.evaluate_javascript("document.title")
        logger.info(f"📍 執行 JS 結果: {result}")
        await browser.semantic_click_by_selector("#login-btn")
        await browser.close()
        logger.info("✅ BrowserCDP 無頭測試通過")
    except Exception as e:
        logger.error(f"❌ BrowserCDP 測試失敗: {e}")

if __name__ == "__main__":
    asyncio.run(run_embodiment_test())
