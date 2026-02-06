import os
import requests
import base64
import urllib3
from typing import Optional, Dict, Any, List

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Siemens PLC Configuration
SIEMENS_PLC_URL = os.getenv("SIEMENS_PLC_URL", "http://192.168.1.100")  # Default PLC IP
SIEMENS_PLC_USERNAME = os.getenv("SIEMENS_PLC_USERNAME", "admin")
SIEMENS_PLC_PASSWORD = os.getenv("SIEMENS_PLC_PASSWORD", "admin")

class SiemensPLCApp:
    """
    Main Siemens PLC handler that processes API requests for reading/writing data
    """

    @staticmethod
    def handle_action(action_json, original_request=""):  # pylint: disable=unused-argument
        """
        Main entry point for Siemens PLC API actions
        """
        action = action_json.get("action")
        params = action_json.get("params", {})

        if not SIEMENS_PLC_URL:
            return {"error": "Siemens PLC URL not configured. Please set SIEMENS_PLC_URL environment variable."}

        handler = SiemensPLCHandler(SIEMENS_PLC_URL, SIEMENS_PLC_USERNAME, SIEMENS_PLC_PASSWORD)

        try:
            if action == "read_variable":
                variable_name = params.get("variable_name")
                if not variable_name:
                    return {"error": "variable_name is required for read_variable action"}
                return handler.read_variable(variable_name)

            elif action == "write_variable":
                variable_name = params.get("variable_name")
                value = params.get("value")

                if not variable_name or value is None:
                    return {"error": "variable_name and value are required for write_variable action"}
                return handler.write_variable(variable_name, value)

            elif action == "browse_variables":
                path = params.get("path", "")
                return handler.browse_variables(path)

            else:
                return {"error": f"Unknown action: {action}"}

        except requests.RequestException as e:
            return {"error": f"Request error: {str(e)}"}
        except (ValueError, KeyError) as e:
            return {"error": f"Data error: {str(e)}"}
        except Exception as e:  # pylint: disable=broad-except
            return {"error": f"Unexpected error: {str(e)}"}

class SiemensPLCHandler:
    """
    Handler for Siemens S7-1500 PLC Webserver API
    """

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.token = None
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        self._login()

    def _login(self):
        """Authenticate with Api.Login and store the session token."""
        login_payload = {
            "jsonrpc": "2.0",
            "method": "Api.Login",
            "params": {
                "user": self.username,
                "password": self.password
            },
            "id": 1
        }
        url = self.base_url if self.base_url.endswith('/api/jsonrpc') else self.base_url + '/api/jsonrpc'
        try:
            response = self.session.post(url, json=login_payload, verify=False, timeout=10)
            response.raise_for_status()
            data = response.json()
            if 'result' in data and 'token' in data['result']:
                self.token = data['result']['token']
                # Use Bearer token in Authorization header
                self.session.headers['Authorization'] = f"Bearer {self.token}"
            elif 'result' in data and isinstance(data['result'], str):
                # Some PLCs may return token as a string directly
                self.token = data['result']
                self.session.headers['Authorization'] = f"Bearer {self.token}"
            else:
                raise Exception(f"Login failed: {data}")
        except Exception as e:
            raise Exception(f"PLC login failed: {e}")

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Make HTTP request to PLC webserver using session token."""
        # Always use the full /api/jsonrpc endpoint
        url = self.base_url if self.base_url.endswith('/api/jsonrpc') else self.base_url + '/api/jsonrpc'
        try:
            if method.upper() == "GET":
                response = self.session.get(url, verify=False, timeout=10)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data, verify=False, timeout=10)
            elif method.upper() == "PUT":
                response = self.session.put(url, json=data, verify=False, timeout=10)
            else:
                return {"error": f"Unsupported HTTP method: {method}"}
            response.raise_for_status()
            try:
                return response.json()
            except ValueError:
                return {"response": response.text, "status_code": response.status_code}
        except requests.exceptions.Timeout:
            return {"error": "Request timeout - PLC may be unreachable"}
        except requests.exceptions.ConnectionError:
            return {"error": "Connection error - Cannot reach PLC"}
        except requests.exceptions.HTTPError as e:
            return {"error": f"HTTP error {e.response.status_code}: {e.response.text}"}
        except requests.exceptions.RequestException as e:
            return {"error": f"Request error: {str(e)}"}
        except Exception as e:  # pylint: disable=broad-except
            return {"error": f"Unexpected error: {str(e)}"}

    def read_variable(self, variable_name: str) -> Dict[str, Any]:
        """Read a single variable from PLC"""
        endpoint = "/api/jsonrpc"

        payload = {
            "jsonrpc": "2.0",
            "method": "PlcProgram.Read",
            "params": {
                "var": variable_name
            },
            "id": 1
        }

        response = self._make_request("POST", endpoint, payload)

        if "result" in response:
            return {
                "variable_name": variable_name,
                "value": response["result"],
                "success": True
            }
        elif "error" in response:
            return {"error": f"Failed to read variable {variable_name}: {response['error']}", "success": False}
        else:
            return {"error": f"Unexpected response for variable {variable_name}", "response": response, "success": False}

    def write_variable(self, variable_name: str, value: Any) -> Dict[str, Any]:
        """Write a single variable to PLC"""
        endpoint = "/api/jsonrpc"

        payload = {
            "jsonrpc": "2.0",
            "method": "PlcProgram.Write",
            "params": {
                "var": variable_name,
                "value": value
            },
            "id": 1
        }

        response = self._make_request("POST", endpoint, payload)

        if "result" in response:
            return {
                "variable_name": variable_name,
                "value": value,
                "success": True,
                "message": "Variable written successfully"
            }
        elif "error" in response:
            return {"error": f"Failed to write variable {variable_name}: {response['error']}", "success": False}
        else:
            return {"error": f"Unexpected response for variable {variable_name}", "response": response, "success": False}

    def browse_variables(self, path: str = "") -> Dict[str, Any]:
        """Browse available variables in PLC"""
        endpoint = "/api/jsonrpc"

        payload = {
            "jsonrpc": "2.0",
            "method": "PlcProgram.Browse",
            "params": {
                "var": path
            },
            "id": 1
        }

        response = self._make_request("POST", endpoint, payload)

        if "result" in response:
            return {
                "path": path,
                "variables": response["result"],
                "success": True
            }
        elif "error" in response:
            return {"error": f"Failed to browse path '{path}': {response['error']}", "success": False}
        else:
            return {"error": f"Unexpected response for path '{path}'", "response": response, "success": False}
