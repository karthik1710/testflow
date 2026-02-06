"""
Testflow Framework - FastAPI Web Server
AI-powered test automation that executes manual web UI test cases from TestRail automatically.

Main Goal: Replace manual testing - AI reads test cases from TestRail and executes them without human intervention.
"""
import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import zipfile
import io

# Setup logging
from testflow.logger import setup_logger
logger = setup_logger("testflow.server", f"logs/server_{datetime.now().strftime('%Y%m%d')}.log", logging.DEBUG)

# Import testflow components
from testflow.agent import Agent
from testflow.gitlab_app.handler import GitLabApp
from testflow.testrail_app.handler import TestRailApp
from testflow.siemens_plc_app.handler import SiemensPLCApp
from testflow.playwright_app.handler import PlaywrightApp
from testflow.database.db_manager import DatabaseManager
from testflow.database.models import TestRun
from testflow.ai_interpreter import AIInterpreter

# Initialize FastAPI
app = FastAPI(
    title="Testflow Framework",
    description="AI-Powered Test Automation Platform",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components
agent = Agent()
agent.register_app("gitlab", GitLabApp)
agent.register_app("testrail", TestRailApp)
agent.register_app("siemens_plc", SiemensPLCApp)
agent.register_app("playwright", PlaywrightApp)

db = DatabaseManager()
ai_interpreter = AIInterpreter()  # Initialize AI interpreter (optional, falls back to rule-based)

# WebSocket connections manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.test_progress: Dict[str, dict] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

    async def send_progress(self, test_id: str, stage: str, progress: int, message: str):
        """Send progress update for specific test"""
        progress_data = {
            "type": "progress",
            "test_id": test_id,
            "stage": stage,
            "progress": progress,
            "message": message,
            "timestamp": datetime.now().isoformat()
        }
        self.test_progress[test_id] = progress_data
        await self.broadcast(progress_data)

manager = ConnectionManager()

# Request/Response Models
class ChatMessage(BaseModel):
    message: str

class TestExecutionRequest(BaseModel):
    test_case_id: str

# Mount static files
frontend_path = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

# ============================================================
# API Routes
# ============================================================

@app.get("/")
async def root():
    """Serve the web UI"""
    return FileResponse(str(frontend_path / "index.html"))

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

@app.get("/api/metrics/summary")
async def get_metrics_summary():
    """Get overall metrics summary"""
    try:
        summary = db.get_metrics_summary(days=30)

        return {
            "totalTests": summary.get('total_tests', 0),
            "passedTests": summary.get('passed_tests', 0),
            "failedTests": summary.get('failed_tests', 0),
            "successRate": summary.get('success_rate', 0),
            "avgDuration": round(summary.get('avg_duration', 0), 2),
            "testsToday": 0,
            "aiCalls": summary.get('ai_calls', 0),
            "cacheHits": summary.get('cache_hits', 0),
            "dailyTrend": summary.get('daily_trend', [])
        }
    except Exception as e:
        print(f"Error getting metrics: {e}")
        return {
            "totalTests": 0,
            "passedTests": 0,
            "failedTests": 0,
            "successRate": 0,
            "avgDuration": 0,
            "testsToday": 0,
            "aiCalls": 0,
            "cacheHits": 0,
            "dailyTrend": []
        }

@app.get("/api/test-runs")
async def get_test_runs(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None
):
    """Get test execution history"""
    try:
        runs = db.get_test_runs(limit=limit, offset=offset, status=status)
        return {"runs": runs, "total": len(runs)}
    except Exception as e:
        print(f"Error getting test runs: {e}")
        return {"runs": [], "total": 0}

@app.get("/api/test-runs/{run_id}/download")
async def download_test_report(run_id: int):
    """Download test report as ZIP (screenshots + JSON)"""
    run = db.get_test_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Test run not found")

    steps = db.get_test_steps(run_id)
    screenshots = db.get_screenshots(run_id)
    
    logger.info(f"Preparing download for run_id={run_id}, found {len(screenshots)} screenshots")
    for screenshot in screenshots:
        logger.debug(f"Screenshot: {screenshot.get('file_path')} - exists: {Path(screenshot.get('file_path', '')).exists() if screenshot.get('file_path') else False}")

    # Create ZIP file in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Add report JSON
        report = {
            "run": run,
            "steps": steps,
            "screenshots": screenshots
        }
        zip_file.writestr("report.json", json.dumps(report, indent=2, default=str))

        # Add screenshot files to zip
        screenshot_count = 0
        for screenshot in screenshots:
            screenshot_path = screenshot.get('file_path')
            if screenshot_path and Path(screenshot_path).exists():
                # Add screenshot with organized folder structure
                file_name = Path(screenshot_path).name
                zip_file.write(screenshot_path, f"screenshots/{file_name}")
                screenshot_count += 1
                logger.debug(f"Added screenshot to zip: {file_name}")
            elif screenshot_path:
                logger.warning(f"Screenshot file not found: {screenshot_path}")

        logger.info(f"Added {screenshot_count} screenshots to zip file")

        # Add README with report summary
        readme_content = f"""Test Execution Report
======================

Test Case ID: {run.get('test_case_id', 'N/A')}
Test Name: {run.get('test_name', 'N/A')}
Status: {run.get('status', 'N/A')}
Duration: {run.get('duration_seconds', 0):.2f}s
Total Steps: {run.get('total_steps', 0)}
Passed Steps: {run.get('passed_steps', 0)}
Failed Steps: {run.get('failed_steps', 0) or (run.get('total_steps', 0) - run.get('passed_steps', 0))}

Execution Time: {run.get('start_time', 'N/A')}
Screenshots Included: {screenshot_count}

Files in this archive:
- report.json: Detailed test execution data
- screenshots/: Test execution screenshots ({screenshot_count} files)
"""
        zip_file.writestr("README.txt", readme_content)

    zip_buffer.seek(0)

    # Generate filename: tc<case_id>_<timestamp>.zip
    test_case_id = run.get('test_case_id', run_id)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"tc{test_case_id}_{timestamp}.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# ============================================================
# WebSocket Routes
# ============================================================

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint for chat interface"""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")

            # Check if it's a test execution command
            if "run test" in message.lower() or "execute test" in message.lower():
                # Extract test case ID
                import re
                match = re.search(r'\d+', message)
                if match:
                    test_id = match.group()

                    # Create test run
                    test_run = TestRun(
                        test_case_id=test_id,
                        test_name=f"Test Case {test_id}",
                        status="RUNNING",
                        start_time=datetime.now()
                    )
                    run_id = db.create_test_run(test_run)

                    # Execute in background
                    asyncio.create_task(execute_test_background(test_id, run_id))

                    await websocket.send_json({
                        "type": "response",
                        "message": f"✅ Started test execution for test case {test_id}"
                    })
                else:
                    await websocket.send_json({
                        "type": "response",
                        "message": "❌ Please provide a test case ID (e.g., 'run test case 596349')"
                    })
            else:
                # Generic AI response
                await websocket.send_json({
                    "type": "response",
                    "message": f"📝 Received: {message}\n🤖 AI processing your request..."
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket)

async def execute_test_background(test_case_id: str, run_id: int):
    """Execute test in background and send progress updates"""
    start_time = datetime.now()

    logger.info(f"Starting test execution for test case {test_case_id}, run_id={run_id}")

    try:
        # Stage 1: Fetch from TestRail
        await manager.send_progress(test_case_id, "fetching", 20, "Fetching test case from TestRail...")
        logger.info(f"Fetching test case {test_case_id} from TestRail")

        # Fetch test case from TestRail
        testrail_result = await agent.handle("testrail", {
            "action": "get_test_case",
            "params": {
                "case_id": test_case_id
            }
        })

        logger.debug(f"TestRail result keys: {list(testrail_result.keys()) if testrail_result else 'None'}")

        if not testrail_result or "error" in testrail_result:
            error_msg = testrail_result.get('error', 'Unknown error') if testrail_result else 'No response from TestRail'
            logger.error(f"Failed to fetch test case {test_case_id}: {error_msg}")
            raise Exception(f"Failed to fetch test case: {error_msg}")

        # Debug: Print what we got from TestRail
        logger.info(f"TestRail Response Keys: {list(testrail_result.keys())}")

        test_case = testrail_result.get("test_case") or testrail_result
        test_name = test_case.get("title", f"Test Case {test_case_id}")

        logger.info(f"Test case name: {test_name}")

        # Try multiple field names for steps
        steps = (
            test_case.get("custom_steps_separated") or
            test_case.get("custom_steps") or
            test_case.get("steps") or
            []
        )

        logger.info(f"Steps found: {len(steps)}")
        logger.debug(f"Steps type: {type(steps)}")

        if not steps:
            logger.warning(f"No steps found! Available fields in test_case: {list(test_case.keys())}")
            logger.debug(f"Test case data: {test_case}")
            # Create a dummy step so execution can proceed
            steps = [{"content": "Default step - no steps found in TestRail"}]
            logger.info("Created dummy step for execution")

        # Update test run with name
        db.update_test_run(run_id, test_name=test_name, total_steps=len(steps))

        # Stage 2: AI Processing
        await manager.send_progress(test_case_id, "ai_processing", 40, f"AI analyzing {len(steps)} test steps...")

        logger.info(f"Processing {len(steps)} test steps")
        logger.debug(f"Steps: {steps}")

        # Try AI interpretation first, fallback to rule-based parsing
        if ai_interpreter.enabled:
            logger.info("🤖 Using OpenAI AI interpretation")
            playwright_actions = ai_interpreter.interpret_multiple_steps(steps, context={})

            if playwright_actions:
                logger.info(f"✅ AI successfully interpreted {len(playwright_actions)} actions")
                # Add description field from original_step for consistency
                for action in playwright_actions:
                    if "original_step" in action and "description" not in action:
                        action["description"] = action["original_step"][:100]
            else:
                logger.warning("⚠️ AI interpretation returned empty, falling back to rule-based")
                playwright_actions = None
        else:
            logger.info("📋 Using rule-based parsing (set OPENAI_API_KEY to enable AI)")
            playwright_actions = None

        # Define HTMLStripper class (used for both rule-based parsing and validation)
        import re
        from html.parser import HTMLParser

        class HTMLStripper(HTMLParser):
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

        # Fallback to rule-based parsing if AI not available or failed
        if not playwright_actions:
            playwright_actions = []
            base_url = None  # Track base URL from first navigation

            for idx, step in enumerate(steps):
                # Handle different step formats from TestRail
                if isinstance(step, dict):
                    step_text = (
                        step.get("content", "") or
                        step.get("description", "") or
                        step.get("step", "") or
                        str(step)
                    )
                    # Extract expected result separately for validation
                    expected_result = step.get("expected", "") or step.get("expected_result", "")
                else:
                    step_text = str(step)
                    expected_result = ""

                # Extract clean text and URLs from HTML
                stripper = HTMLStripper()
                try:
                    stripper.feed(step_text)
                    clean_text = ' '.join(stripper.text).strip()
                except:
                    clean_text = step_text

                logger.debug(f"Parsing step {idx+1}: {clean_text}")

                # Check for navigation keywords
                if "navigate" in clean_text.lower() or "open" in clean_text.lower() or "go to" in clean_text.lower():
                    url = None

                    # Try to get URL from HTML links first
                    if stripper.links:
                        url = stripper.links[0]
                        logger.debug(f"Found URL in HTML link: {url}")
                    else:
                        # Try to find full URL in text
                        url_match = re.search(r'https?://[^\s<>"]+', step_text)
                        if url_match:
                            url = url_match.group()
                            logger.debug(f"Found full URL: {url}")
                        else:
                            # Look for relative paths like /abp, /calibration
                            path_match = re.search(r'/[a-zA-Z0-9_-]+', clean_text)
                            if path_match:
                                if base_url:
                                    url = base_url.rstrip('/') + path_match.group()
                                    logger.debug(f"Constructed URL from base: {url}")
                                else:
                                    url = path_match.group()
                                    logger.debug(f"Found relative path: {url}")

                    if url:
                        # Save base URL from first navigation
                        if not base_url and url.startswith('http'):
                            base_match = re.match(r'(https?://[^/]+)', url)
                            if base_match:
                                base_url = base_match.group(1)
                                logger.info(f"Base URL set to: {base_url}")

                        playwright_actions.append({
                            "action": "navigate",
                            "params": {"url": url},
                            "description": clean_text[:100],
                            "expected": expected_result
                        })
                        logger.debug(f"→ Navigate action: {url}")
                    else:
                        playwright_actions.append({
                            "action": "wait",
                            "params": {"timeout": 1000},
                            "description": clean_text[:100],
                            "expected": expected_result
                        })
                        logger.debug(f"→ Wait action (no URL found)")

                elif "click" in clean_text.lower() or "select" in clean_text.lower():
                    # Try to extract element text to click
                    text_match = re.search(r'[`"\']([^`"\']+)[`"\']', clean_text)
                    if text_match:
                        playwright_actions.append({
                            "action": "click",
                            "params": {"text": text_match.group(1)},
                            "description": clean_text[:100],
                            "expected": expected_result
                        })
                        logger.debug(f"→ Click action: {text_match.group(1)}")
                    else:
                        playwright_actions.append({
                            "action": "wait",
                            "params": {"timeout": 1000},
                            "description": clean_text[:100],
                            "expected": expected_result
                        })
                        logger.debug(f"→ Wait action (click target not found)")

                else:
                    # For all other steps, add a wait action
                    playwright_actions.append({
                        "action": "wait",
                        "params": {"timeout": 1000},
                        "description": clean_text[:100],
                        "expected": expected_result
                    })
                    logger.debug(f"→ Wait action (generic step)")

        logger.info(f"Generated {len(playwright_actions)} Playwright actions via {'AI' if ai_interpreter.enabled and playwright_actions else 'rule-based parsing'}")

        if not playwright_actions:
            # Create at least one dummy action
            playwright_actions.append({
                "action": "wait",
                "params": {"timeout": 1000},
                "description": "Default action"
            })

        # Stage 3: AI Processing Complete
        await manager.send_progress(test_case_id, "ai_processing", 50, f"AI interpretation complete: {len(playwright_actions)} actions generated")
        await asyncio.sleep(0.5)  # Brief pause to show progress

        # Stage 4: Execution
        await manager.send_progress(test_case_id, "executing", 60, f"Executing {len(playwright_actions)} actions...")

        passed_steps = 0
        failed_steps = 0

        # Execute each action
        for idx, action in enumerate(playwright_actions):
            step_progress = 60 + int((idx + 1) / len(playwright_actions) * 30)
            await manager.send_progress(
                test_case_id,
                "executing",
                step_progress,
                f"Executing step {idx + 1}/{len(playwright_actions)}: {action.get('action', 'unknown')}"
            )

            # Execute the action
            exec_result = await agent.handle("playwright", {
                "action": action.get("action"),
                "params": action.get("params", {})
            })

            # Validate expected results if provided
            validation_passed = True
            validation_message = ""
            expected_result = action.get("expected", "")

            if expected_result and expected_result.strip():
                # Extract clean text from expected result HTML
                stripper = HTMLStripper()
                try:
                    stripper.feed(expected_result)
                    expected_text = ' '.join(stripper.text).strip()
                except:
                    expected_text = expected_result

                logger.debug(f"Validating expected result: {expected_text}")

                # Get comprehensive page content for validation
                page_validation = await agent.handle("playwright", {
                    "action": "get_page_content_for_validation",
                    "params": {}
                })

                if page_validation.get("success"):
                    page_data = page_validation.get("page_data", {})

                    # Format page data for AI analysis
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
                else:
                    # Fallback to simple text extraction
                    page_validation_fallback = await agent.handle("playwright", {
                        "action": "get_text",
                        "params": {}
                    })
                    page_content = page_validation_fallback.get("text", "")

                # Use AI to intelligently validate expected result
                validation_context = {
                    "action_performed": action.get("action"),
                    "step_description": action.get("description", ""),
                    "action_params": action.get("params", {})
                }

                validation_result = ai_interpreter.validate_expected_result(
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

                # Log reasoning for debugging
                if validation_result.get("reasoning"):
                    logger.debug(f"Validation reasoning: {validation_result['reasoning']}")
                if validation_result.get("extracted_value"):
                    logger.debug(f"Extracted value: {validation_result['extracted_value']}")

            # Record step in database
            # If validation passes, consider the step PASSED (end result matters for testing)
            # If no validation required, use execution success
            has_validation = expected_result and expected_result.strip()
            if has_validation:
                step_status = "PASSED" if validation_passed else "FAILED"
            else:
                step_status = "PASSED" if exec_result.get("success") else "FAILED"

            from testflow.database.models import TestStep
            test_step = TestStep(
                test_run_id=run_id,
                step_number=idx + 1,
                description=action.get("description", str(action)),
                action_type=action.get("action"),
                action_params=str(action.get("params", {})),
                status=step_status,
                error_message=validation_message if not validation_passed else None,
                screenshot_path=exec_result.get("screenshot", ""),
                execution_time_ms=int(exec_result.get("duration", 0) * 1000)
            )
            step_id = db.create_test_step(test_step)

            # Save screenshot if available
            if exec_result.get("screenshot"):
                from testflow.database.models import Screenshot
                from pathlib import Path
                screenshot_path = exec_result.get("screenshot")
                screenshot_file = Path(screenshot_path)
                screenshot = Screenshot(
                    test_run_id=run_id,
                    test_step_id=step_id,
                    file_path=screenshot_path,
                    file_name=screenshot_file.name,
                    file_size_bytes=screenshot_file.stat().st_size if screenshot_file.exists() else 0
                )
                db.create_screenshot(screenshot)

            if step_status == "PASSED":
                passed_steps += 1
            else:
                failed_steps += 1

            # Send step update to UI
            await manager.broadcast({
                "type": "step",
                "step": f"Step {idx + 1}: {action.get('action', 'unknown')}",
                "status": "success" if step_status == "PASSED" else "failed"
            })

        # Stage 4: Complete
        duration = (datetime.now() - start_time).total_seconds()
        final_status = "PASSED" if failed_steps == 0 else "FAILED"

        logger.info(f"Test execution complete: {final_status}, duration={duration}s, passed={passed_steps}, failed={failed_steps}")

        await manager.send_progress(
            test_case_id,
            "complete",
            100,
            f"✅ Test complete! {passed_steps} passed, {failed_steps} failed"
        )

        # Update database
        db.update_test_run(
            run_id,
            status=final_status,
            end_time=datetime.now(),
            duration_seconds=duration,
            passed_steps=passed_steps,
            total_steps=len(playwright_actions)
        )

        # Update metrics
        tests_passed = 1 if final_status == "PASSED" else 0
        tests_failed = 1 if final_status == "FAILED" else 0
        db.update_daily_metrics(
            tests_run=1,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            duration=duration,
            ai_calls=1
        )

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Test execution error for case {test_case_id}: {error_msg}", exc_info=True)

        await manager.send_progress(test_case_id, "error", 0, f"❌ Error: {error_msg}")

        duration = (datetime.now() - start_time).total_seconds()
        db.update_test_run(
            run_id,
            status="FAILED",
            end_time=datetime.now(),
            duration_seconds=duration
        )
        db.update_daily_metrics(tests_run=1, tests_failed=1, duration=duration)

# ============================================================
# Startup/Shutdown Events
# ============================================================

@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    print("=" * 70)
    print("🚀 Testflow Framework - AI-Powered Test Automation")
    print("=" * 70)
    print("📋 Main Goal: Execute manual web UI test cases from TestRail")
    print("              automatically without human intervention")
    print("=" * 70)
    print("📊 Database: SQLite initialized")
    print(f"🤖 AI: OpenAI {'enabled' if ai_interpreter.enabled else 'disabled (set OPENAI_API_KEY to enable)'}")
    print("🌐 Web UI: http://localhost:8000")
    print("💡 Tip: Copy .env.example to .env and configure TestRail credentials")
    print("=" * 70)

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    print("👋 Testflow Framework shutting down...")
