"""
Services Package
Contains business logic services separated from HTTP routing
"""

from .test_execution_service import TestExecutionService
from .validation_service import ValidationService
from .screenshot_service import ScreenshotService

__all__ = [
    'TestExecutionService',
    'ValidationService',
    'ScreenshotService'
]


class HTMLStripper(HTMLParser):
    """Strip HTML tags from text"""

    def __init__(self):
        super().__init__()
        self.text = []
        self.links = []

    def handle_data(self, data):
        self.text.append(data)

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            for attr, value in attrs:
                if attr == 'href':
                    self.links.append(value)


class TestExecutionService:
    """
    Service for managing test execution lifecycle
    """

    def __init__(self, agent, db_manager, ai_interpreter):
        """
        Initialize test execution service

        Args:
            agent: Agent instance for handling actions
            db_manager: Database manager for persistence
            ai_interpreter: AI interpreter for intelligent validation
        """
        self.agent = agent
        self.db = db_manager
        self.ai_interpreter = ai_interpreter

    async def execute_test_case(
        self,
        test_case_id: int,
        test_case_data: Dict[str, Any],
        progress_callback=None
    ) -> Dict[str, Any]:
        """
        Execute a complete test case

        Args:
            test_case_id: TestRail test case ID
            test_case_data: Test case data including steps
            progress_callback: Optional callback for progress updates

        Returns:
            Execution result dictionary
        """
        start_time = datetime.now()

        # Create test run record
        from testflow.database.models import TestRun
        test_run = TestRun(
            test_case_id=test_case_id,
            test_name=test_case_data.get('title', f'Test {test_case_id}'),
            status='RUNNING',
            start_time=start_time.isoformat()
        )
        run_id = self.db.create_test_run(test_run)

        logger.info(f"Starting test execution for test case {test_case_id}, run_id={run_id}")

        try:
            # Parse test steps
            steps = test_case_data.get('steps', [])
            total_steps = len(steps)

            if progress_callback:
                await progress_callback("fetching", 20, f"Fetched {total_steps} test steps")

            # Interpret steps with AI
            playwright_actions = await self._interpret_steps(steps, progress_callback)

            if not playwright_actions:
                raise Exception("No actions generated from test steps")

            if progress_callback:
                await progress_callback("ai_processing", 50, f"Generated {len(playwright_actions)} actions")

            # Execute actions
            passed_steps, failed_steps = await self._execute_actions(
                run_id, playwright_actions, progress_callback
            )

            # Finalize test run
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            status = "PASSED" if failed_steps == 0 else "FAILED"

            self.db.update_test_run(
                run_id,
                status=status,
                end_time=end_time.isoformat(),
                duration_seconds=duration,
                total_steps=total_steps,
                passed_steps=passed_steps,
                failed_steps=failed_steps
            )

            logger.info(f"Test execution complete: {status}, duration={duration:.2f}s, passed={passed_steps}, failed={failed_steps}")

            if progress_callback:
                await progress_callback("complete", 100, f"Test {status}")

            return {
                "success": True,
                "run_id": run_id,
                "status": status,
                "passed_steps": passed_steps,
                "failed_steps": failed_steps,
                "duration": duration
            }

        except Exception as e:
            logger.error(f"Test execution failed: {e}")
            self.db.update_test_run(run_id, status="ERROR", error_message=str(e))

            if progress_callback:
                await progress_callback("error", 100, f"Error: {str(e)}")

            return {
                "success": False,
                "run_id": run_id,
                "error": str(e)
            }

    async def _interpret_steps(
        self,
        steps: List[Dict[str, Any]],
        progress_callback=None
    ) -> List[Dict[str, Any]]:
        """
        Interpret test steps into Playwright actions

        Args:
            steps: Raw test steps from TestRail
            progress_callback: Optional progress callback

        Returns:
            List of Playwright actions
        """
        if progress_callback:
            await progress_callback("interpreting", 30, "Interpreting test steps with AI")

        # Use AI interpreter if available
        if self.ai_interpreter and self.ai_interpreter.enabled:
            logger.info("🤖 Using OpenAI AI interpretation")
            playwright_actions = self.ai_interpreter.interpret_steps(steps)
        else:
            logger.info("📋 Using rule-based interpretation")
            playwright_actions = self._rule_based_interpret(steps)

        if progress_callback:
            await progress_callback("ai_processing", 40, f"Interpreted {len(playwright_actions)} actions")

        return playwright_actions

    def _rule_based_interpret(self, steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Fallback rule-based interpretation

        Args:
            steps: Raw test steps

        Returns:
            List of actions
        """
        actions = []
        for step in steps:
            content = step.get('content', '')
            expected = step.get('expected', '')

            # Simple keyword matching
            if 'navigate' in content.lower() or 'go to' in content.lower():
                # Extract URL
                import re
                url_match = re.search(r'https?://[^\s<>"]+|www\.[^\s<>"]+', content)
                if url_match:
                    actions.append({
                        "action": "navigate",
                        "params": {"url": url_match.group()},
                        "expected": expected,
                        "description": content
                    })
            elif 'click' in content.lower():
                # Default click action
                actions.append({
                    "action": "wait",
                    "params": {"timeout": 1000},
                    "expected": expected,
                    "description": content
                })

        return actions

    async def _execute_actions(
        self,
        run_id: int,
        actions: List[Dict[str, Any]],
        progress_callback=None
    ) -> tuple:
        """
        Execute Playwright actions and validate results

        Args:
            run_id: Test run ID
            actions: List of actions to execute
            progress_callback: Optional progress callback

        Returns:
            Tuple of (passed_steps, failed_steps)
        """
        passed_steps = 0
        failed_steps = 0
        total_actions = len(actions)

        for idx, action in enumerate(actions):
            step_progress = 60 + int((idx + 1) / total_actions * 30)

            if progress_callback:
                await progress_callback(
                    "executing",
                    step_progress,
                    f"Executing step {idx + 1}/{total_actions}: {action.get('action', 'unknown')}"
                )

            # Execute action
            exec_result = await self.agent.handle("playwright", {
                "action": action.get("action"),
                "params": action.get("params", {})
            })

            # Validate expected results
            validation_passed, validation_message = await self._validate_expected_result(
                action.get("expected", ""),
                action,
                exec_result
            )

            # Determine step status
            has_validation = action.get("expected", "").strip()
            if has_validation:
                step_status = "PASSED" if validation_passed else "FAILED"
            else:
                step_status = "PASSED" if exec_result.get("success") else "FAILED"

            # Record step in database
            step_id = await self._record_test_step(
                run_id, idx + 1, action, exec_result, step_status, validation_message
            )

            # Record screenshot
            if exec_result.get("screenshot"):
                await self._record_screenshot(run_id, step_id, exec_result.get("screenshot"))

            if step_status == "PASSED":
                passed_steps += 1
            else:
                failed_steps += 1

        return passed_steps, failed_steps

    async def _validate_expected_result(
        self,
        expected_result: str,
        action: Dict[str, Any],
        exec_result: Dict[str, Any]
    ) -> tuple:
        """
        Validate expected result using AI

        Args:
            expected_result: Expected result text
            action: Action that was executed
            exec_result: Execution result

        Returns:
            Tuple of (validation_passed, validation_message)
        """
        if not expected_result or not expected_result.strip():
            return True, ""

        # Extract clean text from HTML
        stripper = HTMLStripper()
        try:
            stripper.feed(expected_result)
            expected_text = ' '.join(stripper.text).strip()
        except:
            expected_text = expected_result

        logger.debug(f"Validating expected result: {expected_text}")

        # Get page content
        page_content = await self._get_page_content_for_validation()

        # Use AI to validate
        validation_context = {
            "action_performed": action.get("action"),
            "step_description": action.get("description", ""),
            "action_params": action.get("params", {})
        }

        validation_result = self.ai_interpreter.validate_expected_result(
            expected_result=expected_text,
            page_content=page_content,
            context=validation_context
        )

        validation_passed = validation_result.get("passed", False)
        validation_message = validation_result.get("message", "")
        confidence = validation_result.get("confidence", 0.0)

        if validation_passed:
            logger.info(f"✅ {validation_message} (confidence: {confidence:.2f})")
        else:
            logger.warning(f"❌ {validation_message} (confidence: {confidence:.2f})")

        if validation_result.get("reasoning"):
            logger.debug(f"Validation reasoning: {validation_result['reasoning']}")
        if validation_result.get("extracted_value"):
            logger.debug(f"Extracted value: {validation_result['extracted_value']}")

        return validation_passed, validation_message

    async def _get_page_content_for_validation(self) -> str:
        """
        Get structured page content for validation

        Returns:
            Formatted page content string
        """
        page_validation = await self.agent.handle("playwright", {
            "action": "get_page_content_for_validation",
            "params": {}
        })

        if page_validation.get("success"):
            page_data = page_validation.get("page_data", {})

            # Format page data
            page_content = f"""Visible Text:
{page_data.get('visible_text', '')}

Form Fields:
"""
            for field in page_data.get('form_fields', []):
                page_content += f"- {field.get('label', 'Unlabeled')} ({field.get('type', 'input')}): {field.get('value', 'empty')}\n"

            page_content += "\nDropdowns:\n"
            for dropdown in page_data.get('dropdowns', []):
                page_content += f"- {dropdown.get('label', dropdown.get('name', 'Unlabeled'))} dropdown:\n"
                page_content += f"  Selected: {dropdown.get('selected_text', 'None')}\n"
                page_content += f"  Options: {', '.join([opt['text'] for opt in dropdown.get('options', [])])}\n"

            page_content += f"\nButtons: {', '.join(page_data.get('buttons', []))}\n"

            return page_content
        else:
            # Fallback to simple text
            page_validation_fallback = await self.agent.handle("playwright", {
                "action": "get_text",
                "params": {}
            })
            return page_validation_fallback.get("text", "")

    async def _record_test_step(
        self,
        run_id: int,
        step_number: int,
        action: Dict[str, Any],
        exec_result: Dict[str, Any],
        status: str,
        validation_message: str
    ) -> int:
        """
        Record test step in database

        Args:
            run_id: Test run ID
            step_number: Step number
            action: Action details
            exec_result: Execution result
            status: Step status
            validation_message: Validation message

        Returns:
            Step ID
        """
        from testflow.database.models import TestStep

        test_step = TestStep(
            test_run_id=run_id,
            step_number=step_number,
            description=action.get("description", str(action)),
            action_type=action.get("action"),
            action_params=str(action.get("params", {})),
            status=status,
            error_message=validation_message if status == "FAILED" else None,
            screenshot_path=exec_result.get("screenshot", ""),
            execution_time_ms=int(exec_result.get("duration", 0) * 1000)
        )

        return self.db.create_test_step(test_step)

    async def _record_screenshot(self, run_id: int, step_id: int, screenshot_path: str):
        """
        Record screenshot in database

        Args:
            run_id: Test run ID
            step_id: Test step ID
            screenshot_path: Path to screenshot file
        """
        from testflow.database.models import Screenshot
        from pathlib import Path

        screenshot_file = Path(screenshot_path)
        if screenshot_file.exists():
            screenshot = Screenshot(
                test_run_id=run_id,
                test_step_id=step_id,
                file_path=screenshot_path,
                file_name=screenshot_file.name,
                file_size_bytes=screenshot_file.stat().st_size
            )
            self.db.create_screenshot(screenshot)
