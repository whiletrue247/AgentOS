"""
06_Embodiment — Browser CDP Runtime (v5.0 SOTA — Playwright)
==============================================================
使用 Playwright 進行瀏覽器自動化：
  - 頁面導航、點擊、輸入
  - JavaScript 執行
  - 截圖 (供 Vision 模型分析)
  - Cookie / Storage 管理

當 Playwright 不可用時退回 mock 模式。
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# 嘗試載入 Playwright
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class BrowserCDP:
    """
    瀏覽器自動化引擎 (v5.0 SOTA)。
    基於 Playwright (Chromium/Firefox/WebKit) 進行無頭/有頭瀏覽器控制。
    """

    def __init__(self):
        self._browser = None
        self._page = None
        self._playwright = None
        backend = "playwright" if PLAYWRIGHT_AVAILABLE else "mock"
        logger.info(f"🌐 BrowserCDP: backend={backend}")

    async def launch(self, headless: bool = True, browser_type: str = "chromium"):
        """啟動瀏覽器實例"""
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("⚠️ Playwright not installed — running in mock mode")
            return

        self._playwright = await async_playwright().start()
        launcher = getattr(self._playwright, browser_type, self._playwright.chromium)
        self._browser = await launcher.launch(headless=headless)
        self._page = await self._browser.new_page()
        logger.info(f"🚀 Browser launched: {browser_type} (headless={headless})")

    async def close(self):
        """關閉瀏覽器"""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._browser = None
        self._page = None
        logger.info("🔒 Browser closed")

    # ----------------------------------------------------------
    # Navigation
    # ----------------------------------------------------------
    async def navigate(self, url: str, wait_until: str = "domcontentloaded") -> str:
        """導航到指定 URL"""
        if self._page:
            await self._page.goto(url, wait_until=wait_until)
            title = await self._page.title()
            logger.info(f"🌐 Navigated to: {url} ({title})")
            return title
        logger.info(f"🌐 [MOCK] Navigate: {url}")
        return "Mock Page Title"

    async def get_page_content(self) -> str:
        """取得當前頁面的文字內容"""
        if self._page:
            return await self._page.inner_text("body")
        return "Mock page content"

    # ----------------------------------------------------------
    # Interaction
    # ----------------------------------------------------------
    async def click_element(self, selector: str, timeout: int = 5000):
        """點擊 CSS 選擇器指定的元素"""
        if self._page:
            await self._page.click(selector, timeout=timeout)
            logger.info(f"🖱️ Clicked: {selector}")
        else:
            logger.info(f"🖱️ [MOCK] Click: {selector}")

    async def type_into(self, selector: str, text: str, delay: int = 50):
        """在指定元素中輸入文字"""
        if self._page:
            await self._page.fill(selector, text)
            logger.info(f"⌨️ Typed into {selector}: {text[:20]}...")
        else:
            logger.info(f"⌨️ [MOCK] Type into {selector}: {text[:20]}...")

    async def press_key(self, key: str):
        """按下鍵盤按鍵"""
        if self._page:
            await self._page.keyboard.press(key)
            logger.info(f"⌨️ Pressed: {key}")
        else:
            logger.info(f"⌨️ [MOCK] Press: {key}")

    # ----------------------------------------------------------
    # Screenshot
    # ----------------------------------------------------------
    async def take_screenshot(self, full_page: bool = False) -> str:
        """截取瀏覽器畫面並回傳 base64"""
        if self._page:
            screenshot_bytes = await self._page.screenshot(full_page=full_page)
            b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            logger.info(f"📸 Browser screenshot: {len(b64)} bytes")
            return b64
        logger.info("📸 [MOCK] Browser screenshot")
        return "base64_mock_browser_screenshot"

    # ----------------------------------------------------------
    # JavaScript
    # ----------------------------------------------------------
    async def evaluate(self, expression: str) -> Any:
        """執行 JavaScript 並回傳結果"""
        if self._page:
            result = await self._page.evaluate(expression)
            logger.info(f"📜 JS eval: {expression[:50]}... → {str(result)[:100]}")
            return result
        logger.info(f"📜 [MOCK] JS eval: {expression[:50]}...")
        return None

    # ----------------------------------------------------------
    # Page Info
    # ----------------------------------------------------------
    async def get_page_info(self) -> Dict[str, Any]:
        """取得當前頁面資訊"""
        if self._page:
            return {
                "url": self._page.url,
                "title": await self._page.title(),
            }
        return {"url": "mock://page", "title": "Mock Page"}
