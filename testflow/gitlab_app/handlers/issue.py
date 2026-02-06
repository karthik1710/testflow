from .base import BaseGitLabHandler

class IssueHandler(BaseGitLabHandler):
    """
    Handler for GitLab Issue operations
    """

    @classmethod
    def can_handle(cls, endpoint, method):
        """Check if this handler can process the endpoint"""
        return "issues" in endpoint and method.upper() in ["GET", "POST", "PUT", "DELETE"]

    @classmethod
    def process_response(cls, raw_response, action_json, original_request=""):
        """
        Process issue-specific responses
        """
        if isinstance(raw_response, dict) and "error" in raw_response:
            return raw_response

        endpoint = action_json.get("endpoint", "")
        params = action_json.get("params", {})
        method = action_json.get("method", "GET")
        project_name = cls.extract_project_name(endpoint)

        # Handle issue creation/updates
        if method.upper() in ["POST", "PUT"]:
            return cls._process_issue_modification(raw_response, method, project_name)

        # Handle issue listing/viewing
        return cls._process_issue_listing(raw_response, params, original_request, project_name)

    @classmethod
    def _process_issue_modification(cls, raw_response, method, project_name):
        """Process issue creation/update response"""
        if isinstance(raw_response, dict):
            if "error" in raw_response:
                return raw_response  # Return error as-is

            issue_id = raw_response.get("iid", raw_response.get("id", "N/A"))
            title = raw_response.get("title", "Untitled")
            state = raw_response.get("state", "unknown")
            web_url = raw_response.get("web_url", "")
            labels = raw_response.get("labels", [])

            action = "created" if method.upper() == "POST" else "updated"
            summary = f"✅ Issue {action} successfully!\n"
            summary += f"  • Issue #{issue_id}: {title}\n"
            summary += f"  • State: {state}\n"
            if labels:
                summary += f"  • Labels: {', '.join(labels)}\n"
            summary += f"  • Project: {project_name}\n"
            if web_url:
                summary += f"  • View: {web_url}"
            return summary
        else:
            return f"Issue response: {raw_response}"

    @classmethod
    def _process_issue_listing(cls, raw_response, params, original_request, project_name):
        """Process issue listing response"""
        if isinstance(raw_response, list):
            count = len(raw_response)
            state = params.get("state", "all")

            # Check if user asked for count
            if "count" in original_request.lower() or "total" in original_request.lower():
                return f"Found {count} {state} issues in {project_name}"

            if count == 0:
                return f"No {state} issues found in {project_name}"

            # Provide detailed summary
            summary = f"Found {count} {state} issues in {project_name}:\n"

            for i, issue in enumerate(raw_response[:5], 1):  # Show first 5
                issue_id = issue.get("iid", issue.get("id", "N/A"))
                title = issue.get("title", "Untitled")
                labels = issue.get("labels", [])
                assignee = issue.get("assignee", {})
                assignee_name = assignee.get("name", "") if assignee else ""

                # Build issue line
                issue_line = f"#{issue_id}: {title}"
                if labels:
                    issue_line += f" [{', '.join(labels[:2])}]"  # Show first 2 labels
                if assignee_name:
                    issue_line += f" (@{assignee_name})"

                summary += f"  {i}. {issue_line}\n"

            if count > 5:
                summary += f"  ... and {count - 5} more"

            return summary
        else:
            # Single issue response
            issue_id = raw_response.get("iid", raw_response.get("id", "N/A"))
            title = raw_response.get("title", "Untitled")
            state = raw_response.get("state", "unknown")
            labels = raw_response.get("labels", [])

            result = f"Issue #{issue_id}: {title} - State: {state}"
            if labels:
                result += f" [Labels: {', '.join(labels)}]"
            return result
