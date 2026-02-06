from datetime import datetime
import re
from .base import BaseGitLabHandler

class PipelineHandler(BaseGitLabHandler):
    """
    Handler for GitLab Pipeline operations
    """

    @classmethod
    def can_handle(cls, endpoint, method):
        """Check if this handler can process the endpoint"""
        return "pipeline" in endpoint and method.upper() in ["GET", "POST"]

    @classmethod
    def process_response(cls, raw_response, action_json, original_request=""):
        """
        Process pipeline-specific responses
        """
        if isinstance(raw_response, dict) and "error" in raw_response:
            return raw_response

        endpoint = action_json.get("endpoint", "")
        method = action_json.get("method", "GET")
        project_name = cls.extract_project_name(endpoint)

        # Handle pipeline creation
        if method.upper() == "POST":
            return cls._process_pipeline_creation(raw_response, project_name)

        # Handle pipeline variables
        if "variables" in endpoint:
            return cls._process_pipeline_variables(raw_response, project_name)

        # Handle pipeline listing/viewing
        return cls._process_pipeline_listing(raw_response, action_json, original_request, project_name)

    @classmethod
    def _process_pipeline_creation(cls, raw_response, project_name):
        """Process pipeline creation response"""
        if isinstance(raw_response, dict):
            if "error" in raw_response:
                return raw_response  # Return error as-is

            pipeline_id = raw_response.get("id", "N/A")
            status = raw_response.get("status", "unknown")
            ref = raw_response.get("ref", "unknown")
            web_url = raw_response.get("web_url", "")
            summary = "✅ Pipeline created successfully!\n"
            summary += f"  • Pipeline ID: #{pipeline_id}\n"
            summary += f"  • Status: {status}\n"
            summary += f"  • Branch/Tag: {ref}\n"
            summary += f"  • Project: {project_name}\n"
            if web_url:
                summary += f"  • View: {web_url}"
            return summary
        else:
            return f"Pipeline creation response: {raw_response}"

    @classmethod
    def _process_pipeline_variables(cls, raw_response, project_name):
        """Process pipeline variables response"""
        if isinstance(raw_response, list):
            count = len(raw_response)
            if count == 0:
                return f"No variables found for pipeline in {project_name}"
            else:
                summary = f"Found {count} variables for pipeline in {project_name}:\n"
                for var in raw_response:
                    key = var.get("key", "unknown")
                    var_type = var.get("variable_type", "env_var")
                    value = var.get("value", "")
                    # Truncate long values
                    display_value = value[:50] + "..." if len(value) > 50 else value
                    summary += f"  • {key} ({var_type}): {display_value}\n"
                return summary
        else:
            key = raw_response.get("key", "unknown")
            var_type = raw_response.get("variable_type", "env_var")
            value = raw_response.get("value", "")
            return f"Variable: {key} ({var_type}) = {value}"

    @classmethod
    def _process_pipeline_listing(cls, raw_response, action_json, original_request, project_name):
        """Process pipeline listing response"""
        params = action_json.get("params", {})

        if isinstance(raw_response, list):
            count = len(raw_response)

            # Check if user asked for count
            if "count" in original_request.lower() or "total" in original_request.lower():
                status_filter = params.get("status", "")
                if status_filter:
                    return f"Found {count} pipelines with status '{status_filter}' in {project_name}"
                else:
                    return f"Found {count} pipelines in {project_name}"

            if count == 0:
                status_filter = params.get("status", "")
                if status_filter:
                    return f"No pipelines with status '{status_filter}' found in {project_name}"
                else:
                    return f"No pipelines found in {project_name}"

            # Check for specific pipeline ID or status requests
            if "id" in original_request.lower() and ("last" in original_request.lower() or "recent" in original_request.lower()):
                return cls._process_last_pipeline_ids(raw_response, original_request, project_name)
            elif "status" in original_request.lower() and ("last" in original_request.lower() or "recent" in original_request.lower()):
                return cls._process_last_pipeline_statuses(raw_response, original_request, project_name)
            elif any(word in original_request.lower() for word in ["list", "id", "ids", "status"]):
                return cls._process_pipeline_list(raw_response, params, project_name)
            else:
                return cls._process_pipeline_overview(raw_response, project_name)
        else:
            # Single pipeline response
            status = raw_response.get("status", "unknown")
            ref = raw_response.get("ref", "unknown")
            pipeline_id = raw_response.get("id", "N/A")
            return f"Pipeline #{pipeline_id} on {ref}: {status}"

    @classmethod
    def _process_last_pipeline_ids(cls, raw_response, original_request, project_name):
        """Process last N pipeline IDs request"""
        count = len(raw_response)
        requested_count = min(count, 10)  # Default to 10 if not specified

        # Try to extract specific count from request
        count_match = re.search(r'last\s+(\d+)', original_request.lower())
        if count_match:
            requested_count = min(int(count_match.group(1)), count)

        summary = f"Last {requested_count} pipeline IDs in {project_name}:\n"
        for i, pipeline in enumerate(raw_response[:requested_count], 1):
            pipeline_id = pipeline.get('id', 'N/A')
            status = pipeline.get('status', 'unknown')
            ref = pipeline.get('ref', 'unknown')
            created_at = pipeline.get('created_at', '')
            # Format date for readability
            date_str = ""
            if created_at:
                try:
                    date_obj = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    date_str = f" - {date_obj.strftime('%Y-%m-%d %H:%M')}"
                except (ValueError, TypeError):
                    pass
            summary += f"  {i}. Pipeline #{pipeline_id} ({status}) on {ref}{date_str}\n"
        return summary

    @classmethod
    def _process_last_pipeline_statuses(cls, raw_response, original_request, project_name):
        """Process last N pipeline statuses request"""
        count = len(raw_response)
        requested_count = min(count, 10)  # Default to 10 if not specified

        # Try to extract specific count from request
        count_match = re.search(r'last\s+(\d+)', original_request.lower())
        if count_match:
            requested_count = min(int(count_match.group(1)), count)

        summary = f"Last {requested_count} pipeline statuses in {project_name}:\n"
        for i, pipeline in enumerate(raw_response[:requested_count], 1):
            pipeline_id = pipeline.get('id', 'N/A')
            status = pipeline.get('status', 'unknown')
            ref = pipeline.get('ref', 'unknown')
            created_at = pipeline.get('created_at', '')
            # Format date for readability
            date_str = ""
            if created_at:
                try:
                    date_obj = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    date_str = f" - {date_obj.strftime('%Y-%m-%d %H:%M')}"
                except (ValueError, TypeError):
                    pass
            summary += f"  {i}. #{pipeline_id}: {status} (on {ref}){date_str}\n"
        return summary

    @classmethod
    def _process_pipeline_list(cls, raw_response, params, project_name):
        """Process general pipeline list request"""
        count = len(raw_response)
        status_filter = params.get("status", "")
        summary = f"Found {count} pipelines"
        if status_filter:
            summary += f" with status '{status_filter}'"
        summary += f" in {project_name}:\n"

        # List pipeline IDs and their statuses
        for pipeline in raw_response:
            pipeline_id = pipeline.get('id', 'N/A')
            status = pipeline.get('status', 'unknown')
            ref = pipeline.get('ref', 'unknown')
            summary += f"  • Pipeline #{pipeline_id}: {status} (on {ref})\n"

        return summary

    @classmethod
    def _process_pipeline_overview(cls, raw_response, project_name):
        """Process general pipeline overview request"""
        count = len(raw_response)

        # Group by status for better overview
        status_counts = {}
        recent_pipelines = []
        for pipeline in raw_response[:5]:
            status = pipeline.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
            recent_pipelines.append(f"#{pipeline.get('id', 'N/A')} ({status}) - {pipeline.get('ref', 'unknown branch')}")

        summary = f"Found {count} pipelines in {project_name}:\n"
        summary += f"Status overview: {dict(status_counts)}\n"
        summary += "Recent pipelines:\n"
        for pipeline in recent_pipelines:
            summary += f"  • {pipeline}\n"
        if count > 5:
            summary += f"  ... and {count - 5} more"
        return summary

    @classmethod
    def handle_special_cases(cls, raw_response, params, original_request=None, project_name="unknown project"):
        """Handle special cases like warning status"""
        # Handle warning status requests (since GitLab API doesn't support it directly)
        if params and params.get("_search_warnings"):
            # Remove the internal flag before processing
            params = dict(params)
            del params["_search_warnings"]

            # For warning detection, we would need to fetch individual pipeline jobs
            # This is a limitation of GitLab API - it doesn't expose warning status directly
            if isinstance(raw_response, list):
                return f"⚠️  GitLab API limitation: Cannot filter pipelines by 'warning' status directly. Found {len(raw_response)} total pipelines in {project_name}. To detect warnings, individual pipeline jobs would need to be checked separately."
            else:
                return "⚠️  GitLab API limitation: Cannot filter pipelines by 'warning' status directly."

        return None
