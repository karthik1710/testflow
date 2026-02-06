"""
Base handler interface for all agent framework integrations
Provides a consistent interface for different automation handlers
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class BaseHandler(ABC):
    """
    Abstract base class for all handlers in the agent framework
    Each integration (Playwright, GitLab, TestRail, etc.) should inherit from this
    """

    def __init__(self, name: str):
        """
        Initialize base handler

        Args:
            name: Handler name for logging and identification
        """
        self.name = name
        self.logger = logging.getLogger(f"testflow.{name}")

    @abstractmethod
    async def initialize(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """
        Initialize the handler with configuration

        Args:
            config: Optional configuration dictionary

        Returns:
            True if initialization successful, False otherwise
        """
        pass

    @abstractmethod
    async def handle_action(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle a specific action

        Args:
            action: Action type to execute
            params: Parameters for the action

        Returns:
            Result dictionary with at minimum:
            - success: bool
            - error: str (if failed)
            - action: str (action type)
            - timestamp: str (ISO format)
        """
        pass

    @abstractmethod
    async def cleanup(self) -> bool:
        """
        Cleanup resources

        Returns:
            True if cleanup successful, False otherwise
        """
        pass

    def validate_params(self, params: Dict[str, Any], required: list) -> Optional[str]:
        """
        Validate required parameters

        Args:
            params: Parameters to validate
            required: List of required parameter names

        Returns:
            Error message if validation fails, None if successful
        """
        missing = [p for p in required if p not in params]
        if missing:
            return f"Missing required parameters: {', '.join(missing)}"
        return None

    def create_response(
        self,
        success: bool,
        action: str,
        data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create standardized response

        Args:
            success: Whether action succeeded
            action: Action type
            data: Optional data to include
            error: Optional error message

        Returns:
            Standardized response dictionary
        """
        from datetime import datetime

        response = {
            "success": success,
            "action": action,
            "timestamp": datetime.now().isoformat()
        }

        if data:
            response.update(data)

        if error:
            response["error"] = error

        return response
