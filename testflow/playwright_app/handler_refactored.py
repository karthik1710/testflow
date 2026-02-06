"""
Refactored Playwright Handler - inherits from BaseHandler
Handles web UI automation actions using Playwright
"""
import os
import json
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from playwright.async_api import async_playwright, Page, Browser, BrowserContext, TimeoutError as PlaywrightTimeoutError

# Import base handler
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from agent_framework.base_handler import BaseHandler

logger = logging.getLogger(__name__)


class PlaywrightHandler(BaseHandler):
    """
    Playwright handler for web UI automation
    Manages browser sessions and executes UI actions
    """

    def __init__(self, name: str = "playwright"):
        super().__init__(name)

        # Browser instance management
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._playwright = None
        self._screenshot_dir = None
        self._logs: List[Dict[str, Any]] = []
        self._is_headless: bool = True

    async def initialize(self, config: Optional[Dict] = None) -> bool:
        """
        Initialize Playwright browser

        Args:
            config: Configuration options
                - headless (bool): Run in headless mode (default: True)
                - browser_type (str): Browser type (chromium, firefox, webkit)
                - viewport (dict): Viewport dimensions
                - screenshot_dir (str): Directory for screenshots

        Returns:
            True if initialization successful
        """
        try:
            config = config or {}
            headless = config.get("headless", True)
            browser_type = config.get("browser_type", "chromium")
            viewport = config.get("viewport", {"width": 1920, "height": 1080})
            screenshot_dir = config.get("screenshot_dir", "test_results")

            self._is_headless = headless

            # Start Playwright
            if self._playwright is None:
                self._playwright = await async_playwright().start()
                self.logger.info("Playwright started")

            # Launch browser
            if self._browser is None:
                if browser_type == "chromium":
                    self._browser = await self._playwright.chromium.launch(headless=headless)
                elif browser_type == "firefox":
                    self._browser = await self._playwright.firefox.launch(headless=headless)
                elif browser_type == "webkit":
                    self._browser = await self._playwright.webkit.launch(headless=headless)
                else:
                    self._browser = await self._playwright.chromium.launch(headless=headless)

                self.logger.info(f"Browser launched: {browser_type} (headless={headless})")

            # Create context
            if self._context is None:
                self._context = await self._browser.new_context(
                    viewport=viewport,
                    record_video_dir=None,
                    ignore_https_errors=True
                )
                self.logger.info("Browser context created")

            # Create page
            if self._page is None:
                self._page = await self._context.new_page()

                # Setup logging
                self._page.on("console", lambda msg: self._log_console(msg))
                self._page.on("pageerror", lambda err: self._log_error(err))

                self.logger.info("Page created")

            # Setup screenshot directory
            if self._screenshot_dir is None:
                self._screenshot_dir = Path(screenshot_dir) / datetime.now().strftime("%Y%m%d_%H%M%S")
                self._screenshot_dir.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"Screenshot directory: {self._screenshot_dir}")

            return True

        except Exception as e:
            self.logger.error(f"Initialization failed: {e}")
            return False

    async def handle_action(self, action: str, params: Dict) -> Dict:
        """
        Execute Playwright action

        Args:
            action: Action name (navigate, click, fill, etc.)
            params: Action parameters

        Returns:
            Result dictionary
        """
        # Ensure browser is initialized
        if self._page is None:
            await self.initialize()

        # Route to specific action handlers
        action_map = {
            "navigate": self._action_navigate,
            "click": self._action_click,
            "fill": self._action_fill,
            "select": self._action_select,
            "wait": self._action_wait,
            "get_text": self._action_get_text,
            "get_page_content_for_validation": self._action_get_page_content,
            "close": self._action_close
        }

        handler = action_map.get(action)
        if not handler:
            return self.create_response(
                success=False,
                action=action,
                error=f"Unknown action: {action}"
            )

        try:
            result = await handler(params)
            return self.create_response(
                success=True,
                action=action,
                data=result
            )
        except Exception as e:
            self.logger.error(f"Action {action} failed: {e}")

            # Take error screenshot
            screenshot = await self._take_screenshot(f"error_{action}")

            return self.create_response(
                success=False,
                action=action,
                error=str(e),
                data={"screenshot": screenshot}
            )

    async def cleanup(self) -> bool:
        """
        Cleanup resources

        Returns:
            True if cleanup successful
        """
        try:
            if self._page:
                await self._page.close()
                self._page = None
            if self._context:
                await self._context.close()
                self._context = None
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None

            self.logger.info("Cleanup complete")
            return True

        except Exception as e:
            self.logger.error(f"Cleanup failed: {e}")
            return False

    # Action handlers

    async def _action_navigate(self, params: Dict) -> Dict:
        """Navigate to URL"""
        validation_error = self.validate_params(params, ["url"])
        if validation_error:
            raise ValueError(validation_error)

        url = params["url"]
        step_name = params.get("step_name", "navigate")

        screenshot = ""
        try:
            await self._page.goto(url, wait_until="networkidle", timeout=30000)
            await self._page.wait_for_timeout(500)
        except Exception as nav_error:
            self.logger.debug(f"Navigation networkidle timeout, trying domcontentloaded: {nav_error}")
            try:
                await self._page.wait_for_load_state("domcontentloaded", timeout=10000)
                await self._page.wait_for_timeout(500)
            except:
                self.logger.debug("domcontentloaded also timed out, continuing anyway")
                await self._page.wait_for_timeout(1000)

        # Take screenshot regardless
        screenshot = await self._take_screenshot(step_name)

        return {
            "url": url,
            "screenshot": screenshot
        }

    async def _action_click(self, params: Dict) -> Dict:
        """Click element"""
        validation_error = self.validate_params(params, ["selector"])
        if validation_error:
            raise ValueError(validation_error)

        selector = params["selector"]
        step_name = params.get("step_name", "click")

        await self._page.click(selector, timeout=10000)
        await self._page.wait_for_timeout(1000)

        screenshot = await self._take_screenshot(step_name)

        return {
            "selector": selector,
            "screenshot": screenshot
        }

    async def _action_fill(self, params: Dict) -> Dict:
        """Fill input field"""
        validation_error = self.validate_params(params, ["selector", "value"])
        if validation_error:
            raise ValueError(validation_error)

        selector = params["selector"]
        value = params["value"]
        step_name = params.get("step_name", "fill")

        await self._page.fill(selector, value, timeout=10000)
        await self._page.wait_for_timeout(500)

        screenshot = await self._take_screenshot(step_name)

        return {
            "selector": selector,
            "value": value,
            "screenshot": screenshot
        }

    async def _action_select(self, params: Dict) -> Dict:
        """Select dropdown option"""
        validation_error = self.validate_params(params, ["selector"])
        if validation_error:
            raise ValueError(validation_error)

        selector = params["selector"]
        value = params.get("value")
        label = params.get("label")
        step_name = params.get("step_name", "select")

        if value:
            await self._page.select_option(selector, value=value, timeout=10000)
        elif label:
            await self._page.select_option(selector, label=label, timeout=10000)
        else:
            raise ValueError("Either 'value' or 'label' must be provided for select action")

        await self._page.wait_for_timeout(500)

        screenshot = await self._take_screenshot(step_name)

        return {
            "selector": selector,
            "selected": value or label,
            "screenshot": screenshot
        }

    async def _action_wait(self, params: Dict) -> Dict:
        """Wait for specified time"""
        timeout = params.get("timeout", 1000)
        await self._page.wait_for_timeout(timeout)

        return {"waited_ms": timeout}

    async def _action_get_text(self, params: Dict) -> Dict:
        """Get page text"""
        text = await self._page.inner_text("body")
        return {"text": text}

    async def _action_get_page_content(self, params: Dict) -> Dict:
        """Get structured page content for validation"""
        try:
            # Extract structured data via JavaScript
            page_data = await self._page.evaluate("""
                () => {
                    // Get all visible text
                    const visible_text = document.body.innerText;

                    // Get form fields
                    const form_fields = Array.from(document.querySelectorAll('input, textarea')).map(field => {
                        const label = field.labels && field.labels[0] ? field.labels[0].innerText : '';
                        return {
                            type: field.type || 'text',
                            name: field.name,
                            id: field.id,
                            value: field.value,
                            label: label,
                            placeholder: field.placeholder
                        };
                    });

                    // Get dropdowns with all options
                    const dropdowns = Array.from(document.querySelectorAll('select')).map(select => {
                        const label = select.labels && select.labels[0] ? select.labels[0].innerText : '';
                        const options = Array.from(select.options).map(opt => ({
                            value: opt.value,
                            text: opt.text
                        }));
                        return {
                            name: select.name,
                            id: select.id,
                            label: label,
                            selected_value: select.value,
                            selected_text: select.options[select.selectedIndex]?.text || '',
                            options: options
                        };
                    });

                    // Get labels
                    const labels = Array.from(document.querySelectorAll('label')).map(l => l.innerText);

                    // Get buttons
                    const buttons = Array.from(document.querySelectorAll('button')).map(b => b.innerText);

                    return {
                        visible_text,
                        form_fields,
                        dropdowns,
                        labels,
                        buttons
                    };
                }
            """)

            return {"page_data": page_data}

        except Exception as e:
            self.logger.warning(f"Failed to extract structured content: {e}")
            # Fallback to simple text
            text = await self._page.inner_text("body")
            return {
                "page_data": {
                    "visible_text": text,
                    "form_fields": [],
                    "dropdowns": [],
                    "labels": [],
                    "buttons": []
                }
            }

    async def _action_close(self, params: Dict) -> Dict:
        """Close browser"""
        await self.cleanup()
        return {"closed": True}

    # Helper methods

    async def _take_screenshot(self, step_name: str) -> str:
        """Take screenshot"""
        if self._page and self._screenshot_dir:
            timestamp = datetime.now().strftime("%H%M%S")
            filename = f"{timestamp}_{step_name.replace(' ', '_')}.png"
            filepath = self._screenshot_dir / filename

            await self._page.screenshot(path=str(filepath), full_page=True)
            self.logger.debug(f"📸 Screenshot: {filename}")

            return str(filepath)
        return ""

    def _log_console(self, msg):
        """Log console messages"""
        self._logs.append({
            "timestamp": datetime.now().isoformat(),
            "type": "console",
            "level": msg.type,
            "text": msg.text
        })

    def _log_error(self, error):
        """Log page errors"""
        self._logs.append({
            "timestamp": datetime.now().isoformat(),
            "type": "error",
            "error": str(error)
        })


# Legacy wrapper for backward compatibility
class PlaywrightApp:
    """Backward compatibility wrapper"""

    _handler: Optional[PlaywrightHandler] = None

    @classmethod
    async def get_handler(cls) -> PlaywrightHandler:
        """Get or create handler instance"""
        if cls._handler is None:
            cls._handler = PlaywrightHandler()
            await cls._handler.initialize()
        return cls._handler

    @classmethod
    async def handle_action_async(cls, action_json, original_request=""):
        """Async entry point for backward compatibility"""
        handler = await cls.get_handler()

        action = action_json.get("action")
        params = action_json.get("params", {})

        try:
            result = await handler.handle_action(action, params)
            return result
        except Exception as e:
            return {"error": f"Playwright execution error: {str(e)}", "traceback": str(e)}

    @classmethod
    def handle_action(cls, action_json, original_request=""):
        """Synchronous wrapper"""
        try:
            loop = asyncio.get_running_loop()
            return asyncio.create_task(cls.handle_action_async(action_json, original_request))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(cls.handle_action_async(action_json, original_request))
            finally:
                loop.close()
