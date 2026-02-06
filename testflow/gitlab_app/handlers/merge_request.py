from .base import BaseGitLabHandler

class MergeRequestHandler(BaseGitLabHandler):
    """
    Handler for GitLab Merge Request operations
    """

    @classmethod
    def can_handle(cls, endpoint, method):
        """Check if this handler can process the endpoint"""
        return "merge_requests" in endpoint and method.upper() in ["GET", "POST", "PUT", "DELETE"]

    @classmethod
    def process_response(cls, raw_response, action_json, original_request=""):
        """
        Process merge request-specific responses
        """
        if isinstance(raw_response, dict) and "error" in raw_response:
            return raw_response

        endpoint = action_json.get("endpoint", "")
        params = action_json.get("params", {})
        method = action_json.get("method", "GET")
        project_name = cls.extract_project_name(endpoint)

        # Handle merge request creation/updates
        if method.upper() in ["POST", "PUT"]:
            return cls._process_merge_request_modification(raw_response, method, project_name)

        # Handle merge request listing/viewing
        return cls._process_merge_request_listing(raw_response, params, original_request, project_name)

    @classmethod
    def _process_merge_request_modification(cls, raw_response, method, project_name):
        """Process merge request creation/update response"""
        if isinstance(raw_response, dict):
            if "error" in raw_response:
                return raw_response  # Return error as-is

            mr_id = raw_response.get("iid", raw_response.get("id", "N/A"))
            title = raw_response.get("title", "Untitled")
            state = raw_response.get("state", "unknown")
            web_url = raw_response.get("web_url", "")
            source_branch = raw_response.get("source_branch", "unknown")
            target_branch = raw_response.get("target_branch", "unknown")

            action = "created" if method.upper() == "POST" else "updated"
            summary = f"✅ Merge request {action} successfully!\n"
            summary += f"  • MR !{mr_id}: {title}\n"
            summary += f"  • State: {state}\n"
            summary += f"  • {source_branch} → {target_branch}\n"
            summary += f"  • Project: {project_name}\n"
            if web_url:
                summary += f"  • View: {web_url}"
            return summary
        else:
            return f"Merge request response: {raw_response}"

    @classmethod
    def _process_merge_request_listing(cls, raw_response, params, original_request, project_name):
        """Process merge request listing response"""
        if isinstance(raw_response, list):
            count = len(raw_response)
            state = params.get("state", "all")

            # Check if user asked for count
            if "count" in original_request.lower() or "total" in original_request.lower():
                return f"Found {count} {state} merge requests in {project_name}"

            if count == 0:
                return f"No {state} merge requests found in {project_name}"

            # Provide detailed summary
            titles = []
            draft_count = 0

            for mr in raw_response[:5]:  # Show first 5
                title = mr.get("title", "Untitled")
                is_draft = mr.get("draft", False) or mr.get("work_in_progress", False)
                if is_draft:
                    title = f"Draft: {title}"
                    draft_count += 1
                titles.append(title)

            summary = f"Found {count} {state} merge requests in {project_name}"
            if draft_count > 0:
                summary += f" ({draft_count} draft)"
            summary += ":\n"

            for i, title in enumerate(titles, 1):
                summary += f"  {i}. {title}\n"

            if count > 5:
                summary += f"  ... and {count - 5} more"

            return summary
        else:
            # Single merge request response
            mr_id = raw_response.get("iid", raw_response.get("id", "N/A"))
            title = raw_response.get("title", "Untitled")
            state = raw_response.get("state", "unknown")
            is_draft = raw_response.get("draft", False) or raw_response.get("work_in_progress", False)
            draft_prefix = "Draft: " if is_draft else ""
            return f"MR !{mr_id}: {draft_prefix}{title} - State: {state}"

    @classmethod
    def get_state_display(cls, state):
        """Get user-friendly display for MR state"""
        state_mapping = {
            "opened": "Open",
            "closed": "Closed",
            "merged": "Merged",
            "locked": "Locked"
        }
        return state_mapping.get(state, state.title())
