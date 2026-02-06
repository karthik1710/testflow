from .base import BaseGitLabHandler

class GenericHandler(BaseGitLabHandler):
    """
    Handler for other GitLab resources (branches, commits, members, packages, etc.)
    """

    @classmethod
    def can_handle(cls, endpoint, method):
        """Check if this handler can process the endpoint"""
        # This is the fallback handler for all other endpoints
        # Suppress unused warnings as this is intentionally a catch-all
        _ = endpoint, method
        return True

    @classmethod
    def process_response(cls, raw_response, action_json, original_request=""):
        """
        Process responses for various GitLab resources
        """
        if isinstance(raw_response, dict) and "error" in raw_response:
            return raw_response

        endpoint = action_json.get("endpoint", "")
        project_name = cls.extract_project_name(endpoint)

        # Route to specific resource handlers
        if "branches" in endpoint:
            return cls._process_branches(raw_response, original_request, project_name)
        elif "commits" in endpoint:
            return cls._process_commits(raw_response, original_request, project_name)
        elif "members" in endpoint:
            return cls._process_members(raw_response, original_request, project_name)
        elif "packages" in endpoint:
            return cls._process_packages(raw_response, original_request, project_name)
        elif "registry" in endpoint or "repositories" in endpoint:
            return cls._process_registry(raw_response, original_request, project_name)
        elif "tags" in endpoint:
            return cls._process_tags(raw_response, original_request, project_name)
        elif endpoint.endswith("/projects") or "/projects" == endpoint:
            return cls._process_projects(raw_response, original_request)
        else:
            return cls._process_default(raw_response, project_name)

    @classmethod
    def _process_branches(cls, raw_response, original_request, project_name):
        """Process branches response"""
        if isinstance(raw_response, list):
            count = len(raw_response)
            if "count" in original_request.lower() or "total" in original_request.lower():
                return f"Found {count} branches in {project_name}"
            else:
                if count == 0:
                    return f"No branches found in {project_name}"
                else:
                    summary = f"Found {count} branches in {project_name}:\n"
                    for branch in raw_response[:5]:
                        name = branch.get("name", "unnamed")
                        protected = "🔒" if branch.get("protected", False) else ""
                        summary += f"  • {name} {protected}\n"
                    if count > 5:
                        summary += f"  ... and {count - 5} more"
                    return summary
        else:
            name = raw_response.get("name", "unnamed")
            protected = "🔒 Protected" if raw_response.get("protected", False) else ""
            return f"Branch: {name} {protected}"

    @classmethod
    def _process_commits(cls, raw_response, original_request, project_name):
        """Process commits response"""
        if isinstance(raw_response, list):
            count = len(raw_response)
            if "count" in original_request.lower() or "total" in original_request.lower():
                return f"Found {count} commits in {project_name}"
            else:
                if count == 0:
                    return f"No commits found in {project_name}"
                else:
                    summary = f"Found {count} commits in {project_name}:\n"
                    for commit in raw_response[:5]:
                        short_sha = commit.get("short_id", commit.get("id", "")[:8] if commit.get("id") else "unknown")
                        message = commit.get("title", commit.get("message", "No message"))[:60]
                        author = commit.get("author_name", "Unknown")
                        summary += f"  • {short_sha} - {message} by {author}\n"
                    if count > 5:
                        summary += f"  ... and {count - 5} more"
                    return summary
        else:
            short_sha = raw_response.get("short_id", raw_response.get("id", "")[:8] if raw_response.get("id") else "unknown")
            message = raw_response.get("title", raw_response.get("message", "No message"))
            author = raw_response.get("author_name", "Unknown")
            return f"Commit {short_sha}: {message} by {author}"

    @classmethod
    def _process_members(cls, raw_response, original_request, project_name):
        """Process members response"""
        if isinstance(raw_response, list):
            count = len(raw_response)
            if "count" in original_request.lower() or "total" in original_request.lower():
                return f"Found {count} members in {project_name}"
            else:
                if count == 0:
                    return f"No members found in {project_name}"
                else:
                    summary = f"Found {count} members in {project_name}:\n"
                    for member in raw_response[:5]:
                        name = member.get("name", "Unknown")
                        username = member.get("username", "unknown")
                        access_level = member.get("access_level", 0)
                        role = {50: "Owner", 40: "Maintainer", 30: "Developer", 20: "Reporter", 10: "Guest"}.get(access_level, "Unknown")
                        summary += f"  • {name} (@{username}) - {role}\n"
                    if count > 5:
                        summary += f"  ... and {count - 5} more"
                    return summary
        else:
            name = raw_response.get("name", "Unknown")
            username = raw_response.get("username", "unknown")
            access_level = raw_response.get("access_level", 0)
            role = {50: "Owner", 40: "Maintainer", 30: "Developer", 20: "Reporter", 10: "Guest"}.get(access_level, "Unknown")
            return f"Member: {name} (@{username}) - {role}"

    @classmethod
    def _process_packages(cls, raw_response, original_request, project_name):
        """Process packages response"""
        if isinstance(raw_response, list):
            count = len(raw_response)
            if "count" in original_request.lower() or "total" in original_request.lower():
                return f"Found {count} packages in {project_name}"
            else:
                if count == 0:
                    return f"No packages found in {project_name}"
                else:
                    summary = f"Found {count} packages in {project_name}:\n"
                    for package in raw_response[:5]:
                        name = package.get("name", "unnamed")
                        version = package.get("version", "unknown")
                        package_type = package.get("package_type", "unknown")
                        summary += f"  • {name} v{version} ({package_type})\n"
                    if count > 5:
                        summary += f"  ... and {count - 5} more"
                    return summary
        else:
            name = raw_response.get("name", "unnamed")
            version = raw_response.get("version", "unknown")
            package_type = raw_response.get("package_type", "unknown")
            return f"Package: {name} v{version} ({package_type})"

    @classmethod
    def _process_registry(cls, raw_response, original_request, project_name):
        """Process container registry response"""
        if isinstance(raw_response, list):
            count = len(raw_response)
            if "count" in original_request.lower() or "total" in original_request.lower():
                return f"Found {count} registry repositories in {project_name}"
            else:
                if count == 0:
                    return f"No registry repositories found in {project_name}"
                else:
                    summary = f"Found {count} registry repositories in {project_name}:\n"
                    for repo in raw_response[:5]:
                        name = repo.get("name", "unnamed")
                        location = repo.get("location", "unknown")
                        summary += f"  • {name} - {location}\n"
                    if count > 5:
                        summary += f"  ... and {count - 5} more"
                    return summary
        else:
            name = raw_response.get("name", "unnamed")
            location = raw_response.get("location", "unknown")
            return f"Registry repository: {name} - {location}"

    @classmethod
    def _process_tags(cls, raw_response, original_request, project_name):
        """Process tags response"""
        if isinstance(raw_response, list):
            count = len(raw_response)
            if "count" in original_request.lower() or "total" in original_request.lower():
                return f"Found {count} tags in {project_name}"
            else:
                if count == 0:
                    return f"No tags found in {project_name}"
                else:
                    summary = f"Found {count} tags in {project_name}:\n"
                    for tag in raw_response[:5]:
                        name = tag.get("name", "unnamed")
                        message = tag.get("message", "No message")[:40] if tag.get("message") else "No message"
                        summary += f"  • {name} - {message}\n"
                    if count > 5:
                        summary += f"  ... and {count - 5} more"
                    return summary
        else:
            name = raw_response.get("name", "unnamed")
            message = raw_response.get("message", "No message")
            return f"Tag: {name} - {message}"

    @classmethod
    def _process_projects(cls, raw_response, original_request):
        """Process projects listing response"""
        if isinstance(raw_response, list):
            count = len(raw_response)
            if "count" in original_request.lower() or "total" in original_request.lower():
                return f"Found {count} projects"
            else:
                if count == 0:
                    return "No projects found"
                else:
                    summary = f"Found {count} projects:\n"
                    for project in raw_response[:5]:
                        name = project.get("name", "Unnamed")
                        path = project.get("path_with_namespace", project.get("path", "unknown"))
                        visibility = project.get("visibility", "unknown")
                        summary += f"  • {name} ({path}) - {visibility}\n"
                    if count > 5:
                        summary += f"  ... and {count - 5} more"
                    return summary
        else:
            name = raw_response.get("name", "Unnamed")
            path = raw_response.get("path_with_namespace", raw_response.get("path", "unknown"))
            visibility = raw_response.get("visibility", "unknown")
            return f"Project: {name} ({path}) - {visibility}"

    @classmethod
    def _process_default(cls, raw_response, project_name):
        """Default processing for unknown endpoints"""
        if isinstance(raw_response, list):
            return f"Retrieved {len(raw_response)} items from {project_name}"
        elif isinstance(raw_response, dict):
            # Show key fields only
            key_fields = ["id", "name", "title", "status", "state", "description", "path", "ref"]
            summary = {}
            for field in key_fields:
                if field in raw_response:
                    summary[field] = raw_response[field]
            return summary if summary else "Request completed successfully"
        else:
            return raw_response
