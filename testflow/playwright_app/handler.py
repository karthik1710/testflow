import os
import json
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from playwright.async_api import async_playwright, Page, Browser, BrowserContext, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

class PlaywrightApp:
    """
    Main Playwright handler that processes web UI automation actions
    """

    @staticmethod
    async def handle_action_async(action_json, original_request=""):
        """
        Async entry point for Playwright UI automation actions
        """
        action = action_json.get("action")
        params = action_json.get("params", {})

        try:
            result = await PlaywrightHandler.execute_action(action, params, original_request)
            return result
        except Exception as e:
            return {"error": f"Playwright execution error: {str(e)}", "traceback": str(e)}

    @staticmethod
    def handle_action(action_json, original_request=""):
        """
        Synchronous wrapper - tries to run async if possible
        """
        try:
            # Check if we're in an event loop
            loop = asyncio.get_running_loop()
            # If we are, create a task and return a future
            return asyncio.create_task(
                PlaywrightApp.handle_action_async(action_json, original_request)
            )
        except RuntimeError:
            # No event loop running, create one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    PlaywrightApp.handle_action_async(action_json, original_request)
                )
                return result
            finally:
                loop.close()


class PlaywrightHandler:
    """
    Async Playwright handler for web UI automation
    Manages browser sessions and executes UI actions
    """

    # Class-level browser instance to reuse across actions
    _browser: Optional[Browser] = None
    _context: Optional[BrowserContext] = None
    _page: Optional[Page] = None
    _playwright = None
    _screenshot_dir = None
    _logs: List[Dict[str, Any]] = []
    _is_headless: bool = True  # Track headless mode

    @classmethod
    async def initialize_browser(cls, headless: bool = True, browser_type: str = "chromium"):
        """Initialize browser if not already initialized"""
        if cls._playwright is None:
            cls._playwright = await async_playwright().start()

        if cls._browser is None:
            # Store headless setting for screenshot logic
            cls._is_headless = headless

            if browser_type == "chromium":
                cls._browser = await cls._playwright.chromium.launch(headless=headless)
            elif browser_type == "firefox":
                cls._browser = await cls._playwright.firefox.launch(headless=headless)
            elif browser_type == "webkit":
                cls._browser = await cls._playwright.webkit.launch(headless=headless)
            else:
                cls._browser = await cls._playwright.chromium.launch(headless=headless)

        if cls._context is None:
            cls._context = await cls._browser.new_context(
                viewport={"width": 1920, "height": 1080},
                record_video_dir=None,  # Can be enabled if needed
                ignore_https_errors=True  # Allow capturing all pages
            )

        if cls._page is None:
            cls._page = await cls._context.new_page()

            # Setup console and error logging
            cls._page.on("console", lambda msg: cls._log_console(msg))
            cls._page.on("pageerror", lambda err: cls._log_error(err))

        # Setup screenshot directory
        if cls._screenshot_dir is None:
            cls._screenshot_dir = Path("test_results") / datetime.now().strftime("%Y%m%d_%H%M%S")
            cls._screenshot_dir.mkdir(parents=True, exist_ok=True)

        return cls._page

    @classmethod
    def _log_console(cls, msg):
        """Log console messages from the page"""
        cls._logs.append({
            "timestamp": datetime.now().isoformat(),
            "type": "console",
            "level": msg.type,
            "text": msg.text
        })

    @classmethod
    def _log_error(cls, error):
        """Log page errors"""
        cls._logs.append({
            "timestamp": datetime.now().isoformat(),
            "type": "error",
            "error": str(error)
        })

    @classmethod
    async def close_browser(cls):
        """Close browser and cleanup"""
        if cls._page:
            await cls._page.close()
            cls._page = None
        if cls._context:
            await cls._context.close()
            cls._context = None
        if cls._browser:
            await cls._browser.close()
            cls._browser = None
        if cls._playwright:
            await cls._playwright.stop()
            cls._playwright = None

    @classmethod
    async def take_screenshot(cls, step_name: str) -> str:
        """Take screenshot using Playwright's native capabilities"""
        if cls._page and cls._screenshot_dir:
            timestamp = datetime.now().strftime("%H%M%S")
            filename = f"{timestamp}_{step_name.replace(' ', '_')}.png"
            filepath = cls._screenshot_dir / filename

            # Use Playwright's native screenshot (captures page content only)
            await cls._page.screenshot(path=str(filepath), full_page=True)
            logger.debug(f"📸 Captured page screenshot: {filename}")

            return str(filepath)
        return ""

    @classmethod
    async def execute_action(cls, action: str, params: Dict[str, Any], original_request: str = "") -> Dict[str, Any]:
        """
        Execute a Playwright action based on the action type
        """
        try:
            # Initialize browser if needed (except for close action)
            if action != "close_browser":
                page = await cls.initialize_browser(
                    headless=params.get("headless", True),
                    browser_type=params.get("browser_type", "chromium")
                )

            # Execute specific action
            if action == "navigate":
                url = params.get("url")
                if not url:
                    return {"error": "url is required for navigate action"}

                step_name = f"navigate_to_{url.replace('://', '_').replace('/', '_')}"
                screenshot = ""

                # Navigate with flexible wait strategy to handle slow/dynamic pages
                try:
                    # Try networkidle first (waits for network to be idle)
                    await page.goto(url, wait_until=params.get("wait_until", "networkidle"), timeout=30000)
                    
                    # Small buffer for any remaining animations/transitions
                    await page.wait_for_timeout(500)
                    
                except Exception as nav_error:
                    # If networkidle times out, the page may still be functional
                    # Try waiting for domcontentloaded instead
                    logger.debug(f"Navigation networkidle timeout, trying domcontentloaded: {nav_error}")
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=10000)
                        await page.wait_for_timeout(500)
                    except:
                        # Even domcontentloaded failed, but page might still be usable
                        logger.debug("domcontentloaded also timed out, continuing anyway")
                        await page.wait_for_timeout(1000)

                # Take screenshot regardless of navigation success
                screenshot = await cls.take_screenshot(step_name)

                return {
                    "success": True,
                    "action": "navigate",
                    "url": url,
                    "current_url": page.url,
                    "title": await page.title(),
                    "screenshot": screenshot,
                    "timestamp": datetime.now().isoformat()
                }

            elif action == "click":
                selector = params.get("selector")
                text = params.get("text")

                if not selector and not text:
                    return {"error": "Either selector or text is required for click action"}

                if text:
                    # Click by text content
                    await page.get_by_text(text, exact=params.get("exact", False)).click(timeout=params.get("timeout", 30000))
                    step_name = f"click_text_{text.replace(' ', '_')}"
                else:
                    # Click by selector
                    await page.click(selector, timeout=params.get("timeout", 30000))
                    step_name = f"click_{selector.replace('#', 'id_').replace('.', 'class_')}"

                # Wait for any network activity to complete after click
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except:
                    # If no network activity, just wait briefly for DOM updates
                    await page.wait_for_timeout(500)

                screenshot = await cls.take_screenshot(step_name)

                return {
                    "success": True,
                    "action": "click",
                    "selector": selector or f"text={text}",
                    "screenshot": screenshot,
                    "timestamp": datetime.now().isoformat()
                }

            elif action == "fill":
                selector = params.get("selector")
                value = params.get("value", "")

                if not selector:
                    return {"error": "selector is required for fill action"}

                await page.fill(selector, value, timeout=params.get("timeout", 30000))
                step_name = f"fill_{selector.replace('#', 'id_').replace('.', 'class_')}"
                screenshot = await cls.take_screenshot(step_name)

                return {
                    "success": True,
                    "action": "fill",
                    "selector": selector,
                    "value": value,
                    "screenshot": screenshot,
                    "timestamp": datetime.now().isoformat()
                }

            elif action == "type":
                selector = params.get("selector")
                text = params.get("text", "")
                delay = params.get("delay", 100)  # Delay between keystrokes in ms

                if not selector:
                    return {"error": "selector is required for type action"}

                await page.type(selector, text, delay=delay, timeout=params.get("timeout", 30000))
                step_name = f"type_{selector.replace('#', 'id_').replace('.', 'class_')}"
                screenshot = await cls.take_screenshot(step_name)

                return {
                    "success": True,
                    "action": "type",
                    "selector": selector,
                    "text": text,
                    "screenshot": screenshot,
                    "timestamp": datetime.now().isoformat()
                }

            elif action == "select":
                selector = params.get("selector")
                value = params.get("value")

                if not selector or not value:
                    return {"error": "selector and value are required for select action"}

                await page.select_option(selector, value, timeout=params.get("timeout", 30000))
                step_name = f"select_{selector.replace('#', 'id_').replace('.', 'class_')}"
                screenshot = await cls.take_screenshot(step_name)

                return {
                    "success": True,
                    "action": "select",
                    "selector": selector,
                    "value": value,
                    "screenshot": screenshot,
                    "timestamp": datetime.now().isoformat()
                }

            elif action == "wait":
                timeout = params.get("timeout", 5000)
                selector = params.get("selector")

                if selector:
                    await page.wait_for_selector(selector, timeout=timeout)
                    step_name = f"wait_for_{selector.replace('#', 'id_').replace('.', 'class_')}"
                else:
                    await page.wait_for_timeout(timeout)
                    step_name = f"wait_{timeout}ms"

                screenshot = await cls.take_screenshot(step_name)

                return {
                    "success": True,
                    "action": "wait",
                    "timeout": timeout,
                    "selector": selector,
                    "screenshot": screenshot,
                    "timestamp": datetime.now().isoformat()
                }

            elif action == "get_text":
                selector = params.get("selector", "body")  # Default to body for full page text

                element = await page.query_selector(selector)
                if element:
                    text = await element.text_content()
                    return {
                        "success": True,
                        "action": "get_text",
                        "selector": selector,
                        "text": text,
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    return {"error": f"Element not found: {selector}"}

            elif action == "get_attribute":
                selector = params.get("selector")
                attribute = params.get("attribute")

                if not selector or not attribute:
                    return {"error": "selector and attribute are required for get_attribute action"}

                value = await page.get_attribute(selector, attribute, timeout=params.get("timeout", 30000))

                return {
                    "success": True,
                    "action": "get_attribute",
                    "selector": selector,
                    "attribute": attribute,
                    "value": value,
                    "timestamp": datetime.now().isoformat()
                }

            elif action == "screenshot":
                step_name = params.get("name", "manual_screenshot")
                full_page = params.get("full_page", True)

                screenshot = await cls.take_screenshot(step_name)

                return {
                    "success": True,
                    "action": "screenshot",
                    "screenshot": screenshot,
                    "full_page": full_page,
                    "timestamp": datetime.now().isoformat()
                }

            elif action == "execute_script":
                script = params.get("script")

                if not script:
                    return {"error": "script is required for execute_script action"}

                result = await page.evaluate(script)

                return {
                    "success": True,
                    "action": "execute_script",
                    "script": script,
                    "result": result,
                    "timestamp": datetime.now().isoformat()
                }

            elif action == "get_page_info":
                title = await page.title()
                url = page.url
                screenshot = await cls.take_screenshot("page_info")

                return {
                    "success": True,
                    "action": "get_page_info",
                    "title": title,
                    "url": url,
                    "screenshot": screenshot,
                    "timestamp": datetime.now().isoformat()
                }

            elif action == "check_element_exists":
                selector = params.get("selector")

                if not selector:
                    return {"error": "selector is required for check_element_exists action"}

                element = await page.query_selector(selector)
                exists = element is not None

                return {
                    "success": True,
                    "action": "check_element_exists",
                    "selector": selector,
                    "exists": exists,
                    "timestamp": datetime.now().isoformat()
                }

            elif action == "hover":
                selector = params.get("selector")

                if not selector:
                    return {"error": "selector is required for hover action"}

                await page.hover(selector, timeout=params.get("timeout", 30000))
                step_name = f"hover_{selector.replace('#', 'id_').replace('.', 'class_')}"
                screenshot = await cls.take_screenshot(step_name)

                return {
                    "success": True,
                    "action": "hover",
                    "selector": selector,
                    "screenshot": screenshot,
                    "timestamp": datetime.now().isoformat()
                }

            elif action == "get_page_content_for_validation":
                """
                Extract comprehensive page content for AI validation
                Gets: visible text, form fields with values, dropdowns with options, labels
                """
                try:
                    # JavaScript to extract structured page content
                    page_data = await page.evaluate("""() => {
                        const data = {
                            visible_text: document.body.innerText,
                            form_fields: [],
                            dropdowns: [],
                            labels: [],
                            buttons: []
                        };

                        // Extract form input fields with their values
                        document.querySelectorAll('input, textarea').forEach(el => {
                            if (el.offsetParent !== null) { // Only visible elements
                                const label = el.labels && el.labels[0] ? el.labels[0].innerText : '';
                                const placeholder = el.placeholder || '';
                                data.form_fields.push({
                                    type: el.type || 'text',
                                    name: el.name || '',
                                    id: el.id || '',
                                    value: el.value || '',
                                    label: label,
                                    placeholder: placeholder
                                });
                            }
                        });

                        // Extract dropdowns with all options
                        document.querySelectorAll('select').forEach(el => {
                            if (el.offsetParent !== null) {
                                const label = el.labels && el.labels[0] ? el.labels[0].innerText : '';
                                const options = Array.from(el.options).map(opt => ({
                                    text: opt.text,
                                    value: opt.value,
                                    selected: opt.selected
                                }));
                                data.dropdowns.push({
                                    name: el.name || '',
                                    id: el.id || '',
                                    label: label,
                                    selected_value: el.value || '',
                                    selected_text: el.selectedOptions[0] ? el.selectedOptions[0].text : '',
                                    options: options
                                });
                            }
                        });

                        // Extract all visible labels
                        document.querySelectorAll('label, th, td, span[class*="label"], div[class*="label"]').forEach(el => {
                            if (el.offsetParent !== null && el.innerText.trim()) {
                                data.labels.push(el.innerText.trim());
                            }
                        });

                        // Extract buttons
                        document.querySelectorAll('button, input[type="button"], input[type="submit"]').forEach(el => {
                            if (el.offsetParent !== null) {
                                data.buttons.push(el.innerText || el.value || '');
                            }
                        });

                        return data;
                    }""")

                    return {
                        "success": True,
                        "action": "get_page_content_for_validation",
                        "page_data": page_data,
                        "timestamp": datetime.now().isoformat()
                    }
                except Exception as e:
                    logger.error(f"Failed to extract page content: {e}")
                    # Fallback to simple text extraction
                    text = await page.text_content("body")
                    return {
                        "success": True,
                        "action": "get_page_content_for_validation",
                        "page_data": {"visible_text": text},
                        "timestamp": datetime.now().isoformat()
                    }

            elif action == "wait":
                timeout = params.get("timeout", 1000)
                await page.wait_for_timeout(timeout)

                return {
                    "success": True,
                    "action": "wait",
                    "duration": timeout,
                    "timestamp": datetime.now().isoformat()
                }

            elif action == "press_key":
                key = params.get("key")

                if not key:
                    return {"error": "key is required for press_key action"}

                await page.keyboard.press(key)
                step_name = f"press_{key}"
                screenshot = await cls.take_screenshot(step_name)

                return {
                    "success": True,
                    "action": "press_key",
                    "key": key,
                    "screenshot": screenshot,
                    "timestamp": datetime.now().isoformat()
                }

            elif action == "get_logs":
                return {
                    "success": True,
                    "action": "get_logs",
                    "logs": cls._logs.copy(),
                    "log_count": len(cls._logs),
                    "timestamp": datetime.now().isoformat()
                }

            elif action == "clear_logs":
                cls._logs.clear()
                return {
                    "success": True,
                    "action": "clear_logs",
                    "timestamp": datetime.now().isoformat()
                }

            elif action == "close_browser":
                await cls.close_browser()
                return {
                    "success": True,
                    "action": "close_browser",
                    "timestamp": datetime.now().isoformat()
                }

            elif action == "execute_test_steps":
                """
                Execute multiple test steps in sequence
                This is the key action for AI-driven test execution
                """
                steps = params.get("steps", [])
                test_name = params.get("test_name", "unnamed_test")

                if not steps:
                    return {"error": "steps array is required for execute_test_steps action"}

                results = []
                failed = False

                for i, step in enumerate(steps):
                    step_action = step.get("action")
                    step_params = step.get("params", {})
                    step_description = step.get("description", f"Step {i+1}")

                    # Execute the step
                    try:
                        result = await cls.execute_action(step_action, step_params, original_request)
                        results.append({
                            "step_number": i + 1,
                            "description": step_description,
                            "action": step_action,
                            "result": result,
                            "status": "passed" if result.get("success") else "failed"
                        })

                        if not result.get("success"):
                            failed = True
                            if params.get("stop_on_failure", True):
                                break

                    except Exception as e:
                        results.append({
                            "step_number": i + 1,
                            "description": step_description,
                            "action": step_action,
                            "error": str(e),
                            "status": "failed"
                        })
                        failed = True
                        if params.get("stop_on_failure", True):
                            break

                # Get all logs
                logs = cls._logs.copy()

                return {
                    "success": not failed,
                    "action": "execute_test_steps",
                    "test_name": test_name,
                    "total_steps": len(steps),
                    "executed_steps": len(results),
                    "passed_steps": len([r for r in results if r["status"] == "passed"]),
                    "failed_steps": len([r for r in results if r["status"] == "failed"]),
                    "results": results,
                    "logs": logs,
                    "screenshot_directory": str(cls._screenshot_dir),
                    "timestamp": datetime.now().isoformat()
                }

            else:
                return {"error": f"Unknown action: {action}"}

        except PlaywrightTimeoutError as e:
            logger.warning(f"Playwright timeout during {action}: {str(e)}")
            screenshot = await cls.take_screenshot(f"timeout_error_{action}")
            return {
                "error": f"Timeout error during {action}: {str(e)}",
                "screenshot": screenshot,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Unexpected error during {action}: {str(e)}")
            screenshot = await cls.take_screenshot(f"error_{action}")
            return {
                "error": f"Error during {action}: {str(e)}",
                "screenshot": screenshot,
                "timestamp": datetime.now().isoformat()
            }
