"""
Example: Using the New Handler Registry

This example shows how to use the refactored handler architecture
"""
import asyncio
import logging
from agent_framework.handler_registry import HandlerRegistry, register_handler, get_handler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


async def example_basic_usage():
    """Basic usage of handler registry"""
    print("\n=== Basic Handler Usage ===\n")

    # Import handler classes
    from testflow.playwright_app.handler_refactored import PlaywrightHandler

    # Register handlers
    register_handler("playwright", PlaywrightHandler)

    # Get handler with configuration
    playwright = await get_handler("playwright", config={
        "headless": True,
        "browser_type": "chromium"
    })

    if playwright:
        # Execute actions
        result = await playwright.handle_action("navigate", {
            "url": "https://example.com",
            "step_name": "navigate_to_example"
        })

        print(f"Navigation result: {result}")

        # Get page content
        content_result = await playwright.handle_action("get_text", {})
        print(f"Page text length: {len(content_result.get('data', {}).get('text', ''))}")

        # Cleanup
        await playwright.cleanup()


async def example_multiple_handlers():
    """Using multiple handlers together"""
    print("\n=== Multiple Handlers ===\n")

    from testflow.playwright_app.handler_refactored import PlaywrightHandler

    # Create registry
    registry = HandlerRegistry()

    # Register multiple handlers
    registry.register_handler_class("playwright", PlaywrightHandler)
    # registry.register_handler_class("testrail", TestRailHandler)
    # registry.register_handler_class("gitlab", GitLabHandler)

    # List available handlers
    print(f"Available handlers: {registry.list_handlers()}")

    # Use handlers through registry
    result = await registry.handle_action(
        handler_name="playwright",
        action="navigate",
        params={"url": "https://example.com"}
    )

    print(f"Result: {result.get('success')}")

    # Cleanup all handlers
    await registry.cleanup_all()


async def example_with_services():
    """Using services with handler registry"""
    print("\n=== Services with Handler Registry ===\n")

    from testflow.playwright_app.handler_refactored import PlaywrightHandler
    from testflow.services import ValidationService
    from testflow.ai_interpreter import AIInterpreter

    # Setup
    register_handler("playwright", PlaywrightHandler)

    # Create services
    ai_interpreter = AIInterpreter()
    validation_service = ValidationService(ai_interpreter)

    # Get handler
    playwright = await get_handler("playwright")

    if playwright:
        # Navigate
        await playwright.handle_action("navigate", {
            "url": "https://example.com"
        })

        # Get page content
        content_result = await playwright.handle_action("get_page_content_for_validation", {})
        page_data = content_result.get("data", {}).get("page_data", {})

        # Format for validation
        page_content = f"""
Visible Text: {page_data.get('visible_text', '')}
Form Fields: {page_data.get('form_fields', [])}
Dropdowns: {page_data.get('dropdowns', [])}
"""

        # Validate using service
        validation_result = await validation_service.validate_expected_result(
            expected_result="Example Domain",
            page_content=page_content,
            context={"action": "navigate"}
        )

        print(f"Validation: {validation_result}")

        # Cleanup
        await playwright.cleanup()


async def example_custom_handler():
    """Creating and registering a custom handler"""
    print("\n=== Custom Handler ===\n")

    from agent_framework.base_handler import BaseHandler
    from typing import Dict, Optional

    class CustomHandler(BaseHandler):
        """Example custom handler"""

        def __init__(self, name: str = "custom"):
            super().__init__(name)
            self.counter = 0

        async def initialize(self, config: Optional[Dict] = None) -> bool:
            self.logger.info("Custom handler initialized")
            return True

        async def handle_action(self, action: str, params: Dict) -> Dict:
            if action == "count":
                self.counter += 1
                return self.create_response(
                    success=True,
                    action=action,
                    data={"count": self.counter}
                )
            elif action == "reset":
                self.counter = 0
                return self.create_response(
                    success=True,
                    action=action,
                    data={"count": self.counter}
                )
            else:
                return self.create_response(
                    success=False,
                    action=action,
                    error=f"Unknown action: {action}"
                )

        async def cleanup(self) -> bool:
            self.logger.info("Custom handler cleanup")
            return True

    # Register custom handler
    register_handler("custom", CustomHandler)

    # Use custom handler
    custom = await get_handler("custom")
    if custom:
        result1 = await custom.handle_action("count", {})
        print(f"Count 1: {result1}")

        result2 = await custom.handle_action("count", {})
        print(f"Count 2: {result2}")

        result3 = await custom.handle_action("reset", {})
        print(f"Reset: {result3}")

        await custom.cleanup()


async def example_error_handling():
    """Error handling with new architecture"""
    print("\n=== Error Handling ===\n")

    from testflow.playwright_app.handler_refactored import PlaywrightHandler

    register_handler("playwright", PlaywrightHandler)

    playwright = await get_handler("playwright")
    if playwright:
        # Try invalid action
        result = await playwright.handle_action("invalid_action", {})
        print(f"Invalid action result: {result}")

        # Try action with missing parameters
        result = await playwright.handle_action("click", {})
        print(f"Missing params result: {result}")

        await playwright.cleanup()


async def main():
    """Run all examples"""
    try:
        await example_basic_usage()
        await example_multiple_handlers()
        await example_with_services()
        await example_custom_handler()
        await example_error_handling()

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
