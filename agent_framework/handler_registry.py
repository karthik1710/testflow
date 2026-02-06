"""
Handler Registry
Manages dynamic loading and registration of handlers
Provides a centralized way to manage all integration handlers
"""
import logging
from typing import Dict, Optional, Type
from agent_framework.base_handler import BaseHandler

logger = logging.getLogger(__name__)


class HandlerRegistry:
    """
    Registry for managing handlers
    """

    def __init__(self):
        """Initialize handler registry"""
        self._handlers: Dict[str, BaseHandler] = {}
        self._handler_classes: Dict[str, Type[BaseHandler]] = {}

    def register_handler_class(self, name: str, handler_class: Type[BaseHandler]):
        """
        Register a handler class

        Args:
            name: Handler name (e.g., 'playwright', 'testrail', 'gitlab')
            handler_class: Handler class (must inherit from BaseHandler)
        """
        if not issubclass(handler_class, BaseHandler):
            raise ValueError(f"Handler class must inherit from BaseHandler: {handler_class}")

        self._handler_classes[name] = handler_class
        logger.info(f"Registered handler class: {name} -> {handler_class.__name__}")

    async def get_handler(self, name: str, config: Optional[Dict] = None) -> Optional[BaseHandler]:
        """
        Get or create handler instance

        Args:
            name: Handler name
            config: Optional configuration for handler initialization

        Returns:
            Handler instance or None if not found
        """
        # Return existing instance if available
        if name in self._handlers:
            return self._handlers[name]

        # Create new instance if class is registered
        if name in self._handler_classes:
            handler_class = self._handler_classes[name]
            handler = handler_class(name)

            # Initialize handler
            if await handler.initialize(config):
                self._handlers[name] = handler
                logger.info(f"Created and initialized handler: {name}")
                return handler
            else:
                logger.error(f"Failed to initialize handler: {name}")
                return None

        logger.warning(f"Handler not found: {name}")
        return None

    async def handle_action(self, handler_name: str, action: str, params: Dict) -> Dict:
        """
        Execute action on handler

        Args:
            handler_name: Handler name
            action: Action name
            params: Action parameters

        Returns:
            Action result
        """
        handler = await self.get_handler(handler_name)
        if not handler:
            return {
                "success": False,
                "error": f"Handler not found: {handler_name}"
            }

        return await handler.handle_action(action, params)

    async def cleanup_all(self):
        """Cleanup all handlers"""
        for name, handler in self._handlers.items():
            try:
                await handler.cleanup()
                logger.info(f"Cleaned up handler: {name}")
            except Exception as e:
                logger.error(f"Failed to cleanup handler {name}: {e}")

        self._handlers.clear()

    def list_handlers(self) -> list:
        """
        Get list of registered handler names

        Returns:
            List of handler names
        """
        return list(self._handler_classes.keys())

    def is_handler_registered(self, name: str) -> bool:
        """
        Check if handler is registered

        Args:
            name: Handler name

        Returns:
            True if handler is registered
        """
        return name in self._handler_classes


# Global registry instance
_registry = HandlerRegistry()


def get_registry() -> HandlerRegistry:
    """Get global handler registry"""
    return _registry


def register_handler(name: str, handler_class: Type[BaseHandler]):
    """
    Register a handler with global registry

    Args:
        name: Handler name
        handler_class: Handler class
    """
    _registry.register_handler_class(name, handler_class)


async def get_handler(name: str, config: Optional[Dict] = None) -> Optional[BaseHandler]:
    """
    Get handler from global registry

    Args:
        name: Handler name
        config: Optional configuration

    Returns:
        Handler instance or None
    """
    return await _registry.get_handler(name, config)
