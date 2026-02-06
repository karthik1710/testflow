import os
from .handlers.base import BaseGitLabHandler
from .handlers.pipeline import PipelineHandler
from .handlers.merge_request import MergeRequestHandler
from .handlers.issue import IssueHandler
from .handlers.generic import GenericHandler

GITLAB_API_KEY = os.getenv("GITLAB_TOKEN")
GITLAB_URL = "https://gitlab.com/api/v4"

class GitLabApp(BaseGitLabHandler):
    """
    Main GitLab handler that dispatches to specific modular handlers
    """

    # List of handlers in order of priority (most specific first)
    HANDLERS = [
        PipelineHandler,
        MergeRequestHandler,
        IssueHandler,
        GenericHandler,  # Always last as it's the fallback
    ]

    @staticmethod
    def handle_action(action_json, original_request=""):
        """
        Main entry point that dispatches to appropriate modular handlers
        """
        method = action_json.get("method", "GET")
        endpoint = action_json.get("endpoint")
        params = action_json.get("params")
        data = action_json.get("data")

        if not endpoint:
            return {"error": "No endpoint specified"}

        # Validate and fix parameters
        params = GitLabApp.validate_and_fix_params(endpoint, params)

        # Encode project paths in endpoints
        endpoint = GitLabApp.encode_project_path(endpoint)

        # Make the API request
        raw_response = GitLabApp._make_api_request(method, endpoint, params, data, original_request)

        # Check for errors
        if isinstance(raw_response, dict) and "error" in raw_response:
            return raw_response

        # Apply date filtering post-processing if needed
        if "last" in original_request.lower() and any(word in original_request.lower() for word in ["day", "days", "hour", "hours"]):
            original_count = len(raw_response) if isinstance(raw_response, list) else 0
            raw_response = GitLabApp.post_process_date_filtering(raw_response, original_request)
            filtered_count = len(raw_response) if isinstance(raw_response, list) else 0
            if original_count != filtered_count:
                print(f"🔍 Date filtering: {original_count} → {filtered_count} items")

        # Find appropriate handler and process response
        for handler_class in GitLabApp.HANDLERS:
            if handler_class.can_handle(endpoint, method):
                processed_response = handler_class.process_response(raw_response, action_json, original_request)

                # Handle special cases like warning status (for pipeline handler)
                if hasattr(handler_class, 'handle_special_cases') and params and params.get("_search_warnings"):
                    project_name = GitLabApp.extract_project_name(endpoint)
                    special_response = handler_class.handle_special_cases(raw_response, params, original_request, project_name)
                    if special_response:
                        return special_response

                return processed_response

        # This should never happen since GenericHandler accepts everything
        return {"error": "No handler found for this endpoint"}

    @staticmethod
    def _make_api_request(method, endpoint, params, data, original_request=""):
        """
        Make the actual API request with proper error handling
        """
        headers = {"PRIVATE-TOKEN": GITLAB_API_KEY}
        url = f"{GITLAB_URL}{endpoint}"

        # Debug output for pipeline creation
        if method.upper() == "POST" and "/pipeline" in endpoint:
            print("🔧 Creating pipeline:")
            print(f"   URL: {url}")
            print(f"   Method: {method}")
            print(f"   Params: {params}")
            print(f"   Data: {data}")

        # Use pagination for GET requests that typically return lists
        if method.upper() == "GET" and any(resource in endpoint for resource in
                                         ["merge_requests", "issues", "commits", "members", "pipelines",
                                          "branches", "tags", "packages", "registry", "repositories"]):
            return GitLabApp.fetch_all_pages(method, url, headers, params, data)
        else:
            # Single request for other endpoints (including POST pipeline creation)
            try:
                if method.upper() == "POST" and "/pipeline" in endpoint:
                    # For pipeline creation, handle ref parameter specially
                    if params and "ref" in params:
                        # GitLab pipeline creation expects 'ref' as query parameter
                        url += f"?ref={params['ref']}"
                        # Remove ref from params to avoid duplication
                        params_copy = dict(params) if params else {}
                        if "ref" in params_copy:
                            del params_copy["ref"]
                        # Use remaining params in the request
                        response = GitLabApp.make_request(method, endpoint, params_copy, data)
                    else:
                        response = GitLabApp.make_request(method, endpoint, params, data)
                else:
                    response = GitLabApp.make_request(method, endpoint, params, data)

                # Handle pipeline creation errors specially
                if method.upper() == "POST" and "/pipeline" in endpoint and isinstance(response, dict) and "error" in response:
                    error_text = response["error"]
                    if "400" in error_text and "empty" in error_text.lower():
                        return {"error": f"❌ Pipeline creation failed: The branch '{params.get('ref', 'unknown')}' has no jobs configured to run. This could be due to:\n  • No .gitlab-ci.yml file on this branch\n  • Pipeline rules excluding this branch\n  • All jobs having 'only' rules that don't match this branch\n\nOriginal error: {error_text}"}
                    elif "404" in error_text:
                        return {"error": f"❌ Pipeline creation failed: Project or branch not found. Please check:\n  • Project path is correct: {endpoint.split('/')[2].replace('%2F', '/')}\n  • Branch '{params.get('ref', 'unknown')}' exists\n  • You have access to this project"}

                return response

            except (ValueError, TypeError, KeyError) as e:
                return {"error": f"Request failed: {str(e)}"}

# Remove the problematic configuration code at the bottom
