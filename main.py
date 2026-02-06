"""
Testflow Framework - CLI and Web UI
AI-powered test automation platform that executes manual web UI test cases from TestRail automatically.

Main Goal: Replace manual testing - AI reads test cases from TestRail and executes them without human intervention.
"""
import sys
import os
import argparse
import asyncio
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from testflow.agent import Agent
from testflow.gitlab_app.handler import GitLabApp
from testflow.testrail_app.handler import TestRailApp
from testflow.siemens_plc_app.handler import SiemensPLCApp
from testflow.playwright_app.handler import PlaywrightApp
from testflow.ai_interpreter import AIInterpreter


def check_testrail_connection():
    """Check if TestRail is accessible"""
    print("\n🔍 Checking TestRail connection...")

    # Check environment variables
    testrail_url = os.getenv("TESTRAIL_URL", "https://esabgrnd.testrail.io")
    testrail_username = os.getenv("TESTRAIL_USERNAME", "karthik.p@esab.co.in")
    testrail_api_key = os.getenv("TESTRAIL_API_KEY")

    if not testrail_api_key:
        print("❌ TESTRAIL_API_KEY not set!")
        print("   Set it with: export TESTRAIL_API_KEY='your-key'")
        return False

    # Test connection
    import requests
    try:
        url = f"{testrail_url}/index.php?/api/v2/get_projects"
        response = requests.get(
            url,
            auth=(testrail_username, testrail_api_key),
            headers={'Content-Type': 'application/json'},
            timeout=10
        )

        if response.status_code == 200:
            projects = response.json()
            project_count = len(projects) if isinstance(projects, list) else len(projects.get('projects', []))
            print(f"✅ TestRail connected! Found {project_count} projects")
            return True
        elif response.status_code == 401:
            print(f"❌ Authentication failed! Check your API key")
            return False
        else:
            print(f"❌ Connection failed! Status: {response.status_code}")
            return False

    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to TestRail")
        return False
    except requests.exceptions.Timeout:
        print(f"❌ Connection timeout")
        return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def start_web_server():
    """Start the web UI server"""
    import uvicorn

    print("🚀 Testflow Framework - Web UI")
    print("=" * 60)

    # Check TestRail connection
    if not check_testrail_connection():
        print("\n⚠️  Warning: TestRail not accessible, but continuing...")
        print("   Some features may not work without TestRail connection\n")

    print("Starting web server...")
    print("🌐 Open http://localhost:8000 in your browser")
    print("=" * 60)

    uvicorn.run(
        "backend.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )


async def start_cli():
    """Start the CLI interface"""
    print("=" * 70)
    print("🚀 Testflow Framework - AI-Powered Test Automation")
    print("=" * 70)

    # Check TestRail connection
    if not check_testrail_connection():
        print("\n⚠️  Warning: TestRail not accessible")
        print("   You can still use the CLI but test execution won't work\n")

    print("\n💡 Quick Start:")
    print("   • Write test cases in plain English in TestRail")
    print("   • Run: 'run test case <ID>'")
    print("   • AI executes automatically with browser automation")
    print("\n📚 Type 'help' for commands, 'exit' to quit")
    print("=" * 70)
    print()

    # Initialize agent with all apps
    agent = Agent()
    agent.register_app("gitlab", GitLabApp)
    agent.register_app("testrail", TestRailApp)
    agent.register_app("siemens_plc", SiemensPLCApp)
    agent.register_app("playwright", PlaywrightApp)

    while True:
        try:
            user_input = input("\n💬 You: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ['exit', 'quit', 'q']:
                print("👋 Goodbye!")
                break

            if user_input.lower() == 'help':
                print_help()
                continue

            # Process the command
            print("\n🤖 AI: Processing your request...\n")

            # Check for test execution commands
            if "run test" in user_input.lower() or "execute test" in user_input.lower():
                await handle_test_execution(agent, user_input)
            else:
                print("ℹ️  Command not recognized. Type 'help' for available commands.")

        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {str(e)}")


async def handle_test_execution(agent: Agent, user_input: str):
    """Handle test execution from CLI"""
    import re

    # Extract test case ID
    match = re.search(r'\d+', user_input)
    if not match:
        print("❌ No test case ID found. Example: 'run test case 105402'")
        return

    test_case_id = match.group()

    print(f"📋 Fetching test case {test_case_id} from TestRail...")

    # Fetch from TestRail
    testrail_result = await agent.handle("testrail", {
        "action": "get_test_case",
        "params": {"case_id": test_case_id}
    })

    if not testrail_result or "error" in testrail_result:
        print(f"❌ Failed to fetch test case: {testrail_result.get('error', 'Unknown error')}")
        return

    # TestRail API returns test case directly, not nested
    test_case = testrail_result
    test_name = test_case.get("title", f"Test Case {test_case_id}")

    # Try multiple field names for steps
    steps = (
        test_case.get("custom_steps_separated") or
        test_case.get("custom_steps") or
        test_case.get("steps") or
        []
    )

    print(f"✅ Test Case: {test_name}")
    print(f"📝 Steps: {len(steps)}")

    if not steps:
        print(f"⚠️  No steps found in test case!")
        print(f"   Available fields: {list(test_case.keys())}")
        return

    print()

    # Initialize AI interpreter
    ai_interpreter = AIInterpreter()

    # Try AI interpretation first, fallback to rule-based parsing
    if ai_interpreter.enabled:
        print("🤖 Using OpenAI AI interpretation...")
        playwright_actions = ai_interpreter.interpret_multiple_steps(steps, context={})

        if playwright_actions:
            print(f"✅ AI successfully interpreted {len(playwright_actions)} actions")
            # Add description field from original_step for consistency
            for action in playwright_actions:
                if "original_step" in action and "description" not in action:
                    action["description"] = action["original_step"][:100]
        else:
            print("⚠️ AI interpretation failed, falling back to rule-based parsing")
            playwright_actions = None
    else:
        print("📋 Using rule-based parsing (set OPENAI_API_KEY to enable AI)")
        playwright_actions = None

    # Fallback to rule-based parsing if AI not available or failed
    if not playwright_actions:
        playwright_actions = []
        base_url = None  # Track base URL from first step

        for idx, step in enumerate(steps):
            if isinstance(step, dict):
                step_text = step.get("content", "") or step.get("description", "") or str(step)
            else:
                step_text = str(step)

            # Strip HTML tags for better parsing
            import html
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

            stripper = HTMLStripper()
            stripper.feed(step_text)
            clean_text = ' '.join(stripper.text).strip()

            print(f"  Step {idx+1}: {clean_text[:80]}...")

            # Check for navigation
            if "navigate" in clean_text.lower() or "open" in clean_text.lower() or "go to" in clean_text.lower():
                # Try to extract URL from links first
                url = None
                if stripper.links:
                    url = stripper.links[0]
                else:
                    # Try to find URL in text
                    url_match = re.search(r'https?://[^\s<>"]+', step_text)
                    if url_match:
                        url = url_match.group()
                    else:
                        # Look for relative paths like /abp, /calibration
                        path_match = re.search(r'/[a-zA-Z0-9_-]+', clean_text)
                        if path_match and base_url:
                            url = base_url.rstrip('/') + path_match.group()
                        elif path_match:
                            # No base URL yet, just use the path
                            url = path_match.group()

                if url:
                    # Save base URL from first navigation
                    if not base_url and url.startswith('http'):
                        # Extract base URL (protocol + domain)
                        base_match = re.match(r'(https?://[^/]+)', url)
                        if base_match:
                            base_url = base_match.group(1)

                    playwright_actions.append({
                        "action": "navigate",
                        "params": {"url": url},
                        "description": clean_text[:100]
                    })
                else:
                    playwright_actions.append({
                        "action": "wait",
                        "params": {"timeout": 1000},
                        "description": clean_text[:100]
                    })
            elif "click" in clean_text.lower() or "select" in clean_text.lower():
                # Try to extract element to click
                text_match = re.search(r'[`"\']([^`"\']+)[`"\']', clean_text)
                if text_match:
                    playwright_actions.append({
                        "action": "click",
                        "params": {"text": text_match.group(1)},
                        "description": clean_text[:100]
                    })
                else:
                    playwright_actions.append({
                        "action": "wait",
                        "params": {"timeout": 1000},
                        "description": clean_text[:100]
                    })
            else:
                playwright_actions.append({
                    "action": "wait",
                    "params": {"timeout": 1000},
                    "description": clean_text[:100]
                })

    mode = "AI-powered" if ai_interpreter.enabled else "rule-based"
    print(f"\n⚡ Executing {len(playwright_actions)} actions ({mode})...\n")

    # Execute actions
    passed = 0
    failed = 0

    for idx, action in enumerate(playwright_actions):
        action_name = action.get("action", "unknown")
        print(f"  [{idx+1}/{len(playwright_actions)}] {action_name}...", end=" ")

        try:
            result = await agent.handle("playwright", {
                "action": action.get("action"),
                "params": action.get("params", {})
            })

            if result.get("success"):
                print("✅")
                passed += 1
            else:
                print(f"❌ {result.get('error', 'Failed')}")
                failed += 1
        except Exception as e:
            print(f"❌ {str(e)}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"📊 Test Execution Complete")
    print(f"   Passed: {passed}")
    print(f"   Failed: {failed}")
    print(f"   Total:  {len(playwright_actions)}")
    print(f"{'='*60}")


def print_help():
    """Print help information"""
    help_text = """
═══════════════════════════════════════════════════════════════════════
📚 Testflow Framework - Available Commands
═══════════════════════════════════════════════════════════════════════

🎯 MAIN GOAL: Execute manual web UI test cases from TestRail automatically

🚀 Test Execution Commands:
  run test case <ID>       Execute a test case from TestRail
  execute test <ID>        Same as above

💡 How It Works:
  1. You write test steps in plain English in TestRail
     Example: "Navigate to homepage", "Click login button"

  2. AI reads and interprets the test case automatically
     - With OPENAI_API_KEY: Uses GPT-4o-mini for smart interpretation
     - Without: Uses rule-based parsing (regex + HTML)

  3. Browser automation executes the steps
     - Opens browser, navigates, clicks, fills forms
     - Takes screenshots at each step
     - Validates expected results automatically

  4. Results stored and reported back
     - Pass/fail status, duration, screenshots
     - Can update TestRail automatically

📝 Examples:
  run test case 105402     Execute test case 105402 from TestRail
  execute test 596349      Execute test case 596349

⚙️  Configuration:
  • TestRail (Required): Set TESTRAIL_URL, TESTRAIL_USERNAME, TESTRAIL_API_KEY
  • OpenAI (Optional): Set OPENAI_API_KEY for AI-powered interpretation
  • Quick setup: Copy .env.example to .env and configure

🌐 Web UI Mode:
  python main.py --web     Start web interface at http://localhost:8000

💬 General:
  help                     Show this help message
  exit, quit, q            Exit the CLI

═══════════════════════════════════════════════════════════════════════
"""
    print(help_text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Testflow Framework - AI-powered test automation",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Start web UI server (default: CLI mode)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging (verbose output)"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=os.getenv("HEADLESS", "false").lower() == "true",
        help="Run browser in headless mode (default: visible browser)"
    )

    args = parser.parse_args()

    # Setup logging level
    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        print("🐛 Debug mode enabled")
    else:
        logging.basicConfig(
            level=logging.INFO,
            format='%(levelname)s: %(message)s'
        )

    # Set headless mode in environment for Playwright
    if not args.headless:
        os.environ["HEADLESS"] = "false"
        print("👁️  Browser will be visible (non-headless mode)")

    if args.web:
        start_web_server()
    else:
        # Run CLI mode
        try:
            asyncio.run(start_cli())
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")

