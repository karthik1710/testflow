"""
Validation Service
Handles AI-powered and rule-based validation of test results
"""
import logging
from typing import Dict, Any, Optional
from html.parser import HTMLParser

logger = logging.getLogger(__name__)


class HTMLStripper(HTMLParser):
    """Strip HTML tags from text"""

    def __init__(self):
        super().__init__()
        self.text = []

    def handle_data(self, data):
        self.text.append(data)


class ValidationService:
    """
    Service for validating test execution results
    """

    def __init__(self, ai_interpreter):
        """
        Initialize validation service

        Args:
            ai_interpreter: AI interpreter for intelligent validation
        """
        self.ai_interpreter = ai_interpreter

    def strip_html(self, html_text: str) -> str:
        """
        Strip HTML tags from text

        Args:
            html_text: HTML text

        Returns:
            Plain text without HTML tags
        """
        stripper = HTMLStripper()
        try:
            stripper.feed(html_text)
            return ' '.join(stripper.text).strip()
        except:
            return html_text

    async def validate_expected_result(
        self,
        expected_result: str,
        page_content: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Validate expected result against page content

        Args:
            expected_result: Expected result text
            page_content: Current page content
            context: Additional context for validation

        Returns:
            Validation result with passed status and details
        """
        if not expected_result or not expected_result.strip():
            return {
                "passed": True,
                "confidence": 1.0,
                "message": "No validation required",
                "reasoning": "No expected result specified"
            }

        # Clean expected text
        expected_text = self.strip_html(expected_result)

        logger.debug(f"Validating: {expected_text}")

        # Use AI interpreter if available
        if self.ai_interpreter and self.ai_interpreter.enabled:
            try:
                validation_result = self.ai_interpreter.validate_expected_result(
                    expected_result=expected_text,
                    page_content=page_content,
                    context=context or {}
                )

                self._log_validation_result(validation_result)
                return validation_result

            except Exception as e:
                logger.error(f"AI validation failed: {e}")
                # Fall back to simple validation

        # Fallback: simple substring matching
        return self._simple_validation(expected_text, page_content)

    def _simple_validation(self, expected_text: str, page_content: str) -> Dict[str, Any]:
        """
        Simple substring-based validation

        Args:
            expected_text: Expected text
            page_content: Page content

        Returns:
            Validation result
        """
        expected_lower = expected_text.lower()
        content_lower = page_content.lower()

        if expected_lower in content_lower:
            return {
                "passed": True,
                "confidence": 0.8,
                "message": f"Found: {expected_text}",
                "reasoning": "Simple substring match"
            }
        else:
            return {
                "passed": False,
                "confidence": 0.8,
                "message": f"Not found: {expected_text}",
                "reasoning": "Simple substring match failed"
            }

    def _log_validation_result(self, validation_result: Dict[str, Any]):
        """
        Log validation result

        Args:
            validation_result: Validation result dictionary
        """
        passed = validation_result.get("passed", False)
        message = validation_result.get("message", "")
        confidence = validation_result.get("confidence", 0.0)

        if passed:
            logger.info(f"✅ {message} (confidence: {confidence:.2f})")
        else:
            logger.warning(f"❌ {message} (confidence: {confidence:.2f})")

        if validation_result.get("reasoning"):
            logger.debug(f"Reasoning: {validation_result['reasoning']}")
        if validation_result.get("extracted_value"):
            logger.debug(f"Extracted: {validation_result['extracted_value']}")
