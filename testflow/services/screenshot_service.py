"""
Screenshot Service
Handles screenshot capture, storage, and retrieval
"""
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class ScreenshotService:
    """
    Service for managing test screenshots
    """

    def __init__(self, db_manager, screenshots_dir: str = "test_results"):
        """
        Initialize screenshot service

        Args:
            db_manager: Database manager for persistence
            screenshots_dir: Base directory for screenshots
        """
        self.db = db_manager
        self.screenshots_dir = Path(screenshots_dir)

    async def save_screenshot(
        self,
        run_id: int,
        step_id: int,
        screenshot_path: str
    ) -> Optional[int]:
        """
        Save screenshot metadata to database

        Args:
            run_id: Test run ID
            step_id: Test step ID
            screenshot_path: Path to screenshot file

        Returns:
            Screenshot ID if saved, None otherwise
        """
        screenshot_file = Path(screenshot_path)

        if not screenshot_file.exists():
            logger.warning(f"Screenshot file not found: {screenshot_path}")
            return None

        try:
            from testflow.database.models import Screenshot

            screenshot = Screenshot(
                test_run_id=run_id,
                test_step_id=step_id,
                file_path=screenshot_path,
                file_name=screenshot_file.name,
                file_size_bytes=screenshot_file.stat().st_size
            )

            screenshot_id = self.db.create_screenshot(screenshot)
            logger.debug(f"Screenshot saved: {screenshot_file.name} (ID: {screenshot_id})")
            return screenshot_id

        except Exception as e:
            logger.error(f"Failed to save screenshot: {e}")
            return None

    async def get_screenshots_for_run(self, run_id: int) -> List[Dict[str, Any]]:
        """
        Get all screenshots for a test run

        Args:
            run_id: Test run ID

        Returns:
            List of screenshot dictionaries
        """
        screenshots = self.db.get_screenshots_by_run(run_id)
        logger.debug(f"Found {len(screenshots)} screenshots for run {run_id}")
        return screenshots

    async def get_existing_screenshots(self, run_id: int) -> List[Dict[str, Any]]:
        """
        Get existing screenshot files for a test run

        Args:
            run_id: Test run ID

        Returns:
            List of existing screenshot dictionaries with file validation
        """
        screenshots = await self.get_screenshots_for_run(run_id)
        existing_screenshots = []

        for screenshot in screenshots:
            file_path = screenshot.get('file_path')
            if file_path and Path(file_path).exists():
                existing_screenshots.append(screenshot)
                logger.debug(f"Screenshot exists: {file_path}")
            else:
                logger.warning(f"Screenshot file missing: {file_path}")

        logger.info(f"Found {len(existing_screenshots)} existing screenshots for run {run_id}")
        return existing_screenshots

    async def cleanup_old_screenshots(self, days: int = 7) -> int:
        """
        Clean up screenshots older than specified days

        Args:
            days: Number of days to keep screenshots

        Returns:
            Number of screenshots deleted
        """
        # This would query for old screenshots and delete them
        # Implementation depends on database schema
        logger.info(f"Cleanup not implemented yet. Would clean screenshots older than {days} days")
        return 0

    def get_screenshot_path(self, run_id: int, step_name: str, timestamp: datetime) -> Path:
        """
        Generate screenshot file path

        Args:
            run_id: Test run ID
            step_name: Step name
            timestamp: Screenshot timestamp

        Returns:
            Path to screenshot file
        """
        run_dir = self.screenshots_dir / f"run_{run_id}"
        run_dir.mkdir(parents=True, exist_ok=True)

        timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
        filename = f"{step_name}_{timestamp_str}.png"

        return run_dir / filename
