import os
import requests
from urllib.parse import quote_plus
from datetime import datetime, timedelta
import re

# GitLab configuration constants
GITLAB_API_KEY = os.getenv("GITLAB_TOKEN")
GITLAB_URL = "https://gitlab.com/api/v4"

class BaseGitLabHandler:
    """
    Base class for all GitLab handlers with common utilities
    """

    @staticmethod
    def post_process_date_filtering(raw_response, original_request, action_json=None):
        """
        Post-process response for date-based filtering when GitLab API doesn't support it
        or when we need more precise filtering.
        """
        if not isinstance(raw_response, list):
            return raw_response

        # Extract time period from original request
        time_pattern = r'last\s+(\d+)\s+(day|days|hour|hours)'
        match = re.search(time_pattern, original_request.lower())

        if not match:
            return raw_response

        amount = int(match.group(1))
        unit = match.group(2)

        # Calculate cutoff time
        now = datetime.now()
        if unit in ['day', 'days']:
            cutoff = now - timedelta(days=amount)
        elif unit in ['hour', 'hours']:
            cutoff = now - timedelta(hours=amount)
        else:
            return raw_response

        # Filter items based on date fields
        filtered_items = []
        for item in raw_response:
            item_date = None

            # Try different date fields based on endpoint
            date_fields = ['created_at', 'updated_at', 'committed_date', 'finished_at']
            for field in date_fields:
                if field in item and item[field]:
                    try:
                        # Parse GitLab's ISO 8601 format
                        item_date = datetime.fromisoformat(item[field].replace('Z', '+00:00'))
                        break
                    except (ValueError, TypeError):
                        continue

            if item_date and item_date >= cutoff:
                filtered_items.append(item)

        return filtered_items

    @staticmethod
    def validate_and_fix_params(endpoint, params):
        """
        Validate and fix common parameter issues for GitLab API
        """
        if not params:
            params = {}

        # Fix common state/status parameter issues
        if "state" in params:
            state_value = params["state"].lower()

            # Handle merge requests endpoints
            if "merge_requests" in endpoint:
                # GitLab MR states: opened, closed, locked, merged
                if state_value in ["open", "active"]:
                    params["state"] = "opened"
                elif state_value in ["close"]:
                    params["state"] = "closed"
                # Keep other valid states as-is: opened, closed, locked, merged

            # Handle issues endpoints
            elif "issues" in endpoint:
                # GitLab issue states: opened, closed
                if state_value in ["open", "active"]:
                    params["state"] = "opened"
                elif state_value in ["close"]:
                    params["state"] = "closed"

        # Handle pipeline status parameter
        if "status" in params and "pipelines" in endpoint:
            status_value = params["status"].lower()

            # GitLab pipeline statuses: created, waiting_for_resource, preparing, pending,
            # running, success, failed, canceled, skipped, manual, scheduled

            # Map common variations to correct GitLab status
            if status_value in ["fail", "failure", "error"]:
                params["status"] = "failed"
            elif status_value in ["pass", "passed", "ok"]:
                params["status"] = "success"
            elif status_value in ["cancelled"]:
                params["status"] = "canceled"
            elif status_value in ["warn", "warning", "warnings"]:
                # GitLab API doesn't support "warning" status, so remove the filter
                # and let post-processing handle warning detection
                del params["status"]
                # Add a flag for post-processing
                params["_search_warnings"] = True
            # Keep other valid statuses as-is: created, waiting_for_resource, preparing,
            # pending, running, success, failed, canceled, skipped, manual, scheduled

        return params

    @staticmethod
    def fetch_all_pages(method, url, headers, params, data, timeout=30):
        """
        Fetch all pages of data from GitLab API using pagination
        """
        all_data = []
        page = 1
        per_page = 20  # GitLab's maximum per_page value

        # Add pagination params
        if not params:
            params = {}
        params["per_page"] = per_page

        while True:
            params["page"] = page

            try:
                response = requests.request(method, url, headers=headers, params=params, json=data, timeout=timeout)

                if response.status_code != 200:
                    if page == 1:
                        # Return error for first page
                        return {"error": f"HTTP {response.status_code}: {response.text}"}
                    else:
                        # Break on subsequent pages (might be end of data)
                        break

                page_data = response.json()

                # Handle both list and single object responses
                if isinstance(page_data, list):
                    if not page_data:  # Empty page means we're done
                        break
                    all_data.extend(page_data)
                else:
                    # Single object response, no pagination needed
                    return page_data

                # Check if we got fewer items than requested (last page)
                if len(page_data) < per_page:
                    break

                page += 1

                # Safety limit to prevent infinite loops
                if page > 100:  # Max 10,000 items
                    break

            except requests.exceptions.RequestException as e:
                if page == 1:
                    return {"error": f"Request failed: {str(e)}"}
                else:
                    break  # Return partial data if we got some pages
            except ValueError as e:
                if page == 1:
                    return {"error": f"Invalid JSON response: {str(e)}"}
                else:
                    break

        return all_data

    @staticmethod
    def extract_project_name(endpoint):
        """Extract project name from endpoint for display purposes"""
        project_name = "unknown project"
        if "/projects/" in endpoint:
            parts = endpoint.split("/")
            projects_index = parts.index("projects")
            if projects_index + 1 < len(parts):
                project_part = parts[projects_index + 1]
                # Decode URL-encoded project names
                project_name = project_part.replace("%2F", "/")
        return project_name

    @staticmethod
    def encode_project_path(endpoint):
        """
        URL encode project paths in endpoints
        """
        if "/projects/" not in endpoint:
            return endpoint

        print(f"🔍 Original endpoint: {endpoint}")
        # Split into parts to find the project identifier
        parts = endpoint.split("/")
        projects_index = parts.index("projects")

        # The project identifier comes after "projects"
        if projects_index + 1 < len(parts):
            project_part = parts[projects_index + 1]
            print(f"🔍 Project part: {project_part}")
            # Check if this looks like a group/project path (has no encoding yet)
            if project_part and not project_part.startswith("%"):
                # For paths like "esab/equipment/edge-program", we need to look ahead
                # and combine multiple parts until we hit a known API endpoint
                project_parts = []
                i = projects_index + 1
                while i < len(parts) and parts[i] not in [
                    "merge_requests", "issues", "members", "pipelines", "commits",
                    "branches", "tags", "packages", "registry", "repositories", "pipeline"
                ]:
                    project_parts.append(parts[i])
                    i += 1

                print(f"🔍 Project parts: {project_parts}")

                if len(project_parts) > 1:  # It's a group/project path
                    project_path = "/".join(project_parts)
                    encoded_project = quote_plus(project_path)
                    print(f"🔍 Encoding '{project_path}' -> '{encoded_project}'")
                    # Rebuild the endpoint
                    new_parts = parts[:projects_index + 1] + [encoded_project] + parts[i:]
                    endpoint = "/".join(new_parts)
                    print(f"🔍 New endpoint: {endpoint}")

        return endpoint

    @staticmethod
    def make_request(method, endpoint, params=None, data=None, timeout=30):
        """
        Make a single request to GitLab API
        """
        headers = {"PRIVATE-TOKEN": GITLAB_API_KEY}
        url = f"{GITLAB_URL}{endpoint}"

        try:
            response = requests.request(method, url, headers=headers, params=params, json=data, timeout=timeout)

            # Check status code
            if response.status_code not in [200, 201, 202]:
                error_text = response.text
                return {"error": f"HTTP {response.status_code}: {error_text}"}

            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": f"Request failed: {str(e)}"}
        except ValueError as e:
            return {"error": f"Invalid JSON response: {str(e)}"}
