"""GitLab payload mappers to domain models."""

import re
from typing import Any

from dora_platform.providers.base import Mapper


class GitLabMapper(Mapper):
    """Map GitLab webhook/API payloads to normalized domain models."""

    @property
    def provider(self) -> str:
        return "gitlab"

    def map_pull_request(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Map GitLab MR payload to normalized PR dict."""
        # Webhook event
        mr = payload.get("object_attributes") or payload
        project = payload.get("project")

        if not mr or not project:
            return None

        # Only process merge request events
        if payload.get("object_kind") and payload["object_kind"] != "merge_request":
            return None

        state = mr.get("state", "opened")
        merged_at = mr.get("merged_at")
        merge_commit_sha = mr.get("merge_commit_sha")

        return {
            "external_id": str(mr["id"]),
            "number": mr["iid"],
            "title": mr["title"],
            "state": state,  # opened, closed, merged
            "draft": mr.get("work_in_progress", False),
            "author_login": mr.get("author", {}).get("username"),
            "author_avatar_url": mr.get("author", {}).get("avatar_url"),
            "base_ref": mr.get("target_branch"),
            "head_ref": mr.get("source_branch"),
            "head_sha": mr.get("last_commit", {}).get("id"),
            "base_sha": None,  # GitLab doesn't expose base SHA directly in MR
            "merge_commit_sha": merge_commit_sha,
            "merged_at": merged_at,
            "merged_by": mr.get("merged_by", {}).get("username") if mr.get("merged_by") else None,
            "created_at": mr.get("created_at"),
            "updated_at": mr.get("updated_at"),
            "closed_at": mr.get("closed_at"),
            "repository_external_id": f"{project['namespace']['path']}/{project['path']}",
            "repository_url": project["web_url"],
            "html_url": mr["url"],
            "raw_data": mr,
        }

    def map_deployment(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Map GitLab deployment payload to normalized deployment dict."""
        # Webhook event
        deployment = payload.get("deployment") or payload
        project = payload.get("project")

        if not deployment or not project:
            return None

        # Only process deployment events
        if payload.get("object_kind") and payload["object_kind"] != "deployment":
            return None

        status = deployment.get("status", "pending")
        environment = deployment.get("environment", {}).get("name", "production")
        sha = deployment.get("sha")
        ref = deployment.get("ref")

        return {
            "external_id": str(deployment["id"]),
            "sha": sha,
            "ref": ref,
            "environment": environment,
            "status": status,
            "statuses": [{"state": status, "created_at": deployment.get("created_at")}],
            "task": "deploy",
            "payload": {},
            "creator_login": deployment.get("user", {}).get("username"),
            "repository_external_id": f"{project['namespace']['path']}/{project['path']}",
            "created_at": deployment.get("created_at"),
            "updated_at": deployment.get("updated_at"),
            "raw_data": deployment,
        }

    def map_incident(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Map GitLab issue (with incident label/type) payload to normalized incident dict."""
        # Webhook event
        issue = payload.get("object_attributes") or payload
        project = payload.get("project")

        if not issue or not project:
            return None

        # Only process issue events
        if payload.get("object_kind") and payload["object_kind"] != "issue":
            return None

        labels = [label["title"] for label in issue.get("labels", [])]
        is_incident = any(
            label.lower() in ("incident", "bug", "outage", "pagerduty", "severity")
            for label in labels
        )
        if not is_incident:
            return None

        return {
            "external_id": str(issue["id"]),
            "number": issue["iid"],
            "title": issue["title"],
            "state": issue["state"],  # opened, closed
            "labels": labels,
            "author_login": issue.get("author", {}).get("username"),
            "assignees": [a["username"] for a in issue.get("assignees", [])],
            "repository_external_id": f"{project['namespace']['path']}/{project['path']}",
            "html_url": issue["url"],
            "created_at": issue.get("created_at"),
            "updated_at": issue.get("updated_at"),
            "closed_at": issue.get("closed_at"),
            "raw_data": issue,
        }

    def map_commits(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract commits from MR merge, push, or deployment payload."""
        commits = []

        # From MR merged event
        if payload.get("object_kind") == "merge_request" and payload.get("object_attributes", {}).get("state") == "merged":
            mr = payload["object_attributes"]
            project = payload.get("project", {})
            commits.append({
                "sha": mr.get("merge_commit_sha"),
                "message": f"Merge MR !{mr['iid']}: {mr['title']}",
                "author_name": mr.get("merged_by", {}).get("username", "unknown"),
                "author_email": None,
                "committed_at": mr.get("merged_at"),
                "repository_external_id": f"{project.get('namespace', {}).get('path', '')}/{project.get('path', '')}",
                "refs": [f"refs/merge-requests/{mr['iid']}/merge"],
                "raw_data": mr,
            })

        # From deployment
        if payload.get("object_kind") == "deployment":
            dep = payload.get("deployment", {})
            project = payload.get("project", {})
            if dep.get("sha"):
                commits.append({
                    "sha": dep["sha"],
                    "message": dep.get("description", "Deployment"),
                    "author_name": dep.get("user", {}).get("username", "unknown"),
                    "author_email": None,
                    "committed_at": dep.get("created_at"),
                    "repository_external_id": f"{project.get('namespace', {}).get('path', '')}/{project.get('path', '')}",
                    "refs": [dep.get("ref", "")],
                    "raw_data": dep,
                })

        # From push event
        if payload.get("object_kind") == "push":
            project = payload.get("project", {})
            repo_id = f"{project.get('namespace', {}).get('path', '')}/{project.get('path', '')}"
            for commit in payload.get("commits", []):
                commits.append({
                    "sha": commit["id"],
                    "message": commit["message"],
                    "author_name": commit["author"]["name"],
                    "author_email": commit["author"].get("email"),
                    "committed_at": commit["timestamp"],
                    "repository_external_id": repo_id,
                    "refs": [payload.get("ref", "")],
                    "raw_data": commit,
                })

        # Filter out None SHA
        return [c for c in commits if c.get("sha")]

    def _extract_sha_from_text(self, text: str) -> list[str]:
        """Extract SHA references from text (for R2 linking)."""
        sha_pattern = r"\b([0-9a-f]{7,40})\b"
        return re.findall(sha_pattern, text, re.IGNORECASE)