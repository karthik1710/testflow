import os
import requests
import re
import logging
from typing import Optional, Dict, Any

# Setup logger
logger = logging.getLogger("testflow.testrail")

# TestRail Configuration
TESTRAIL_API_KEY = os.getenv("TESTRAIL_API_KEY")
TESTRAIL_URL = os.getenv("TESTRAIL_URL", "https://esabgrnd.testrail.io")
TESTRAIL_USERNAME = os.getenv("TESTRAIL_USERNAME", "karthik.p@esab.co.in")

class TestRailApp:
    """
    Main TestRail handler that processes API requests
    """

    @staticmethod
    def handle_action(action_json, original_request=""):
        """
        Main entry point for TestRail API actions
        """
        action = action_json.get("action")
        params = action_json.get("params", {})

        if not TESTRAIL_API_KEY:
            return {"error": "TestRail API key not configured. Please set TESTRAIL_API_KEY environment variable."}

        handler = TestRailHandler(TESTRAIL_URL, TESTRAIL_USERNAME, TESTRAIL_API_KEY)

        try:
            if action == "get_test_cases":
                project_id = params.get("project_id")
                suite_id = params.get("suite_id")
                if not project_id:
                    return {"error": "project_id is required for get_test_cases action"}
                return handler.get_test_cases(project_id, suite_id)

            elif action == "get_test_case":
                case_id = params.get("case_id")
                if not case_id:
                    return {"error": "case_id is required for get_test_case action"}
                return handler.get_test_case(case_id)

            elif action == "run_test_case":
                run_id = params.get("run_id")
                case_id = params.get("case_id")
                status_id = params.get("status_id")
                comment = params.get("comment", "")

                if not all([run_id, case_id, status_id]):
                    return {"error": "run_id, case_id, and status_id are required for run_test_case action"}

                return handler.run_test_case(run_id, case_id, status_id, comment)

            elif action == "get_projects":
                return handler.get_projects()

            elif action == "get_runs":
                project_id = params.get("project_id")
                if not project_id:
                    return {"error": "project_id is required for get_runs action"}
                return handler.get_runs(project_id)

            elif action == "get_suites":
                project_id = params.get("project_id")
                if not project_id:
                    return {"error": "project_id is required for get_suites action"}
                return handler.get_suites(project_id)

            elif action == "create_run":
                project_id = params.get("project_id")
                suite_id = params.get("suite_id")
                name = params.get("name")
                if not all([project_id, suite_id, name]):
                    return {"error": "project_id, suite_id, and name are required for create_run action"}
                return handler.create_run(project_id, suite_id, name)

            elif action == "cli":
                # Execute TestRail CLI command for complex queries
                command = params.get("command")
                if not command:
                    return {"error": "command is required for cli action"}
                return handler.execute_cli(command)

            else:
                return {"error": f"Unknown action: {action}"}

        except (requests.RequestException, ValueError, KeyError) as e:
            return {"error": f"TestRail API error: {str(e)}"}

class TestRailHandler:
    def __init__(self, base_url: str, username: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.auth = (username, api_key)
        self.headers = {'Content-Type': 'application/json'}

    def get_test_cases(self, project_id: int, suite_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Fetch test cases for a given project ID and optional suite ID."""
        if suite_id:
            url = f"{self.base_url}/index.php?/api/v2/get_cases/{project_id}&suite_id={suite_id}"
        else:
            # Get all suites first, then get cases from first suite
            suites = self.get_suites(project_id)
            if not suites or not suites.get('suites'):
                return {"error": "No test suites found in project"}

            first_suite_id = suites['suites'][0]['id']
            url = f"{self.base_url}/index.php?/api/v2/get_cases/{project_id}&suite_id={first_suite_id}"

        response = requests.get(url, auth=self.auth, headers=self.headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Failed to fetch test cases: {response.status_code} {response.text}")
            return None

    def get_test_case(self, case_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a specific test case by its ID."""
        url = f"{self.base_url}/index.php?/api/v2/get_case/{case_id}"

        logger.info(f"Fetching test case {case_id} from TestRail")
        logger.debug(f"URL: {url}")

        try:
            response = requests.get(url, auth=self.auth, headers=self.headers, timeout=10)

            logger.debug(f"Response status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()

                logger.info(f"Successfully fetched test case {case_id}")
                logger.debug(f"Response keys: {list(data.keys())}")

                # Check for steps in various fields
                steps_fields = ['custom_steps_separated', 'custom_steps', 'steps']
                for field in steps_fields:
                    if field in data:
                        field_value = data[field]
                        if field_value:
                            logger.info(f"Found steps in field '{field}': {len(field_value) if isinstance(field_value, list) else 'not a list'}")
                            logger.debug(f"{field} content: {field_value}")
                        else:
                            logger.warning(f"Field '{field}' exists but is empty")

                # Log if no steps found
                if not any(data.get(field) for field in steps_fields):
                    logger.warning(f"No test steps found for case {case_id}")
                    logger.debug(f"Available fields: {list(data.keys())}")
                    logger.debug(f"Full response: {data}")

                return data
            else:
                logger.error(f"Failed to fetch test case {case_id}: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return None

        except requests.exceptions.Timeout:
            logger.error(f"Timeout while fetching test case {case_id}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request exception while fetching test case {case_id}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error while fetching test case {case_id}: {str(e)}", exc_info=True)
            return None

    def run_test_case(self, run_id: int, case_id: int, status_id: int, comment: str = "") -> Optional[Dict[str, Any]]:
        """Add a result for a test case in a test run."""
        url = f"{self.base_url}/index.php?/api/v2/add_result_for_case/{run_id}/{case_id}"
        data = {"status_id": status_id, "comment": comment}
        response = requests.post(url, json=data, auth=self.auth, headers=self.headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Failed to run test case: {response.status_code} {response.text}")
            return None

    def get_projects(self) -> Optional[Dict[str, Any]]:
        """Fetch all projects."""
        url = f"{self.base_url}/index.php?/api/v2/get_projects"
        response = requests.get(url, auth=self.auth, headers=self.headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Failed to fetch projects: {response.status_code} {response.text}")
            return None

    def get_runs(self, project_id: int) -> Optional[Dict[str, Any]]:
        """Fetch test runs for a given project ID."""
        url = f"{self.base_url}/index.php?/api/v2/get_runs/{project_id}"
        response = requests.get(url, auth=self.auth, headers=self.headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Failed to fetch test runs: {response.status_code} {response.text}")
            return None

    def get_suites(self, project_id: int) -> Optional[Dict[str, Any]]:
        """Fetch test suites for a given project ID."""
        url = f"{self.base_url}/index.php?/api/v2/get_suites/{project_id}"
        response = requests.get(url, auth=self.auth, headers=self.headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Failed to fetch test suites: {response.status_code} {response.text}")
            return None

    def create_run(self, project_id: int, suite_id: int, name: str) -> Optional[Dict[str, Any]]:
        """Create a new test run."""
        url = f"{self.base_url}/index.php?/api/v2/add_run/{project_id}"
        data = {"suite_id": suite_id, "name": name}
        response = requests.post(url, json=data, auth=self.auth, headers=self.headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Failed to create test run: {response.status_code} {response.text}")
            return None

    def execute_cli(self, command: str) -> Dict[str, Any]:
        """Execute TestRail CLI-style commands for complex queries."""
        try:
            # Parse the command to extract what we need
            if "steps" in command.lower() and ("case" in command.lower() or re.search(r'\b\d{6}\b', command)):
                # Extract case ID from command like "Get testcases step of 596349 in 34"
                case_match = re.search(r'\b(\d{6})\b', command)
                if case_match:
                    case_id = case_match.group(1)

                    # Get the test case details
                    result = self.get_test_case(int(case_id))
                    if result:
                        steps_info = self._extract_steps_from_case(result)
                        return {
                            "case_id": case_id,
                            "title": result.get('title', 'Unknown'),
                            "steps": steps_info,
                            "total_steps": len(steps_info)
                        }
                    else:
                        return {"error": f"Could not retrieve test case {case_id}"}
                else:
                    return {"error": "Could not extract case ID from command"}

            # Handle project queries
            elif "projects" in command.lower():
                result = self.get_projects()
                return result if result else {"error": "Failed to get projects"}

            # Handle suites queries
            elif "suites" in command.lower():
                project_match = re.search(r'project\s+(\d+)|in\s+(\d+)', command.lower())
                if project_match:
                    project_id = project_match.group(1) or project_match.group(2)
                    result = self.get_suites(int(project_id))
                    return result if result else {"error": f"Failed to get suites for project {project_id}"}

            return {"error": f"Could not parse command: {command}"}

        except (ValueError, KeyError) as e:
            return {"error": f"CLI execution error: {str(e)}"}

    def _extract_steps_from_case(self, case_data: Dict[str, Any]) -> list:
        """Extract formatted steps from test case data."""
        steps = []

        if case_data.get('custom_steps_separated'):
            for i, step in enumerate(case_data['custom_steps_separated'], 1):
                content = step.get('content', '').strip()
                expected = step.get('expected', '').strip()

                step_info = {
                    "step_number": i,
                    "content": content,
                    "expected_result": expected if expected else None
                }
                steps.append(step_info)

        elif case_data.get('custom_steps'):
            # Handle single step format
            steps.append({
                "step_number": 1,
                "content": case_data['custom_steps'],
                "expected_result": None
            })

        return steps
