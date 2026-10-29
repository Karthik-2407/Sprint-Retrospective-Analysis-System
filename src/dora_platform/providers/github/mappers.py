"""GitHub payload mappers to domain models."""

import re
from typing import Any

from dora_platform.providers.base import Mapper


class GitHubMapper(Mapper):
    """Map GitHub webhook/API payloads to normalized domain models."""

    @property
    def provider(self) -> str:
        return "github"

    def map_pull_request(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Map GitHub PR payload to normalized PR dict."""
        action = payload.get("action")
        pr = payload.get("pull_request")
        if not pr:
            return None

        repo = payload.get("repository")
        if not repo:
            return None

        # Extract merge commit SHA if merged
        merge_commit_sha = None
        merged_at = None
        if pr.get("merged_at"):
            merged_at = pr["merged_at"]
            merge_commit_sha = pr.get("merge_commit_sha")

        return {
            "external_id": str(pr["id"]),
            "number": pr["number"],
            "title": pr["title"],
            "state": pr["state"],  # open, closed
            "draft": pr.get("draft", False),
            "author_login": pr["user"]["login"],
            "author_avatar_url": pr["user"].get("avatar_url"),
            "base_ref": pr["base"]["ref"],
            "head_ref": pr["head"]["ref"],
            "head_sha": pr["head"]["sha"],
            "base_sha": pr["base"]["sha"],
            "merge_commit_sha": merge_commit_sha,
            "merged_at": merged_at,
            "merged_by": pr["merged_by"]["login"] if pr.get("merged_by") else None,
            "created_at": pr["created_at"],
            "updated_at": pr["updated_at"],
            "closed_at": pr.get("closed_at"),
            "repository_external_id": f"{repo['owner']['login']}/{repo['name']}",
            "repository_url": repo["html_url"],
            "html_url": pr["html_url"],
            "raw_data": pr,
        }

    def map_deployment(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Map GitHub deployment/deployment_status payload to normalized deployment dict."""
        event_type = "deployment_status" if payload.get("deployment_status") else "deployment"
        deployment = payload.get("deployment")
        repo = payload.get("repository")
        if not deployment or not repo:
            return None

        # Extract environment and SHA
        environment = deployment.get("environment", "production")
        sha = deployment.get("sha")
        ref = deployment.get("ref")

        # For deployment_status events, get status
        status = "pending"
        statuses = []
        if event_type == "deployment_status":
            dep_status = payload.get("deployment_status", {})
            status = dep_status.get("state", "pending")
            statuses.append({
                "state": status,
                "description": dep_status.get("description"),
                "environment_url": dep_status.get("environment_url"),
                "created_at": dep_status.get("created_at"),
            })

        return {
            "external_id": str(deployment["id"]),
            "sha": sha,
            "ref": ref,
            "environment": environment,
            "status": status,
            "statuses": statuses,
            "task": deployment.get("task", "deploy"),
            "payload": deployment.get("payload", {}),
            "creator_login": deployment.get("creator", {}).get("login"),
            "repository_external_id": f"{repo['owner']['login']}/{repo['name']}",
            "created_at": deployment.get("created_at"),
            "updated_at": deployment.get("updated_at"),
            "raw_data": deployment,
        }

    def map_incident(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Map GitHub issue (with incident label) payload to normalized incident dict."""
        action = payload.get("action")
        issue = payload.get("issue")
        repo = payload.get("repository")
        if not issue or not repo:
            return None

        # Only process if incident-related label
        labels = [label["name"] for label in issue.get("labels", [])]
        is_incident = any(
            label.lower() in ("incident", "bug", "outage", "pagerduty", "sev-")
            for label in labels
        )
        if not is_incident:
            return None

        return {
            "external_id": str(issue["id"]),
            "number": issue["number"],
            "title": issue["title"],
            "state": issue["state"],  # open, closed
            "labels": labels,
            "author_login": issue["user"]["login"],
            "assignees": [a["login"] for a in issue.get("assignees", [])],
            "repository_external_id": f"{repo['owner']['login']}/{repo['name']}",
            "html_url": issue["html_url"],
            "created_at": issue["created_at"],
            "updated_at": issue["updated_at"],
            "closed_at": issue.get("closed_at"),
            "raw_data": issue,
        }

    def map_commits(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract commits from PR merge, push, or deployment payload."""
        commits = []

        # From PR merged event
        if payload.get("pull_request") and payload["pull_request"].get("merged_at"):
            pr = payload["pull_request"]
            commits.append({
                "sha": pr.get("merge_commit_sha"),
                "message": f"Merge PR #{pr['number']}: {pr['title']}",
                "author_name": pr.get("merged_by", {}).get("login", "unknown"),
                "author_email": None,
                "committed_at": pr["merged_at"],
                "repository_external_id": f"{payload.get('repository', {}).get('owner', {}).get('login', '')}/{payload.get('repository', {}).get('name', '')}",
                "refs": [f"refs/pull/{pr['number']}/merge"],
                "raw_data": pr,
            })

        # From deployment
        if payload.get("deployment"):
            dep = payload["deployment"]
            if dep.get("sha"):
                commits.append({
                    "sha": dep["sha"],
                    "message": dep.get("description", "Deployment"),
                    "author_name": dep.get("creator", {}).get("login", "unknown"),
                    "author_email": None,
                    "committed_at": dep.get("created_at"),
                    "repository_external_id": f"{payload.get('repository', {}).get('owner', {}).get('login', '')}/{payload.get('repository', {}).get('name', '')}",
                    "refs": [dep.get("ref", "")],
                    "raw_data": dep,
                })

        # From push event (if present)
        if "commits" in payload:
            repo = payload.get("repository", {})
            repo_id = f"{repo.get('owner', {}).get('login', '')}/{repo.get('name', '')}"
            for commit in payload["commits"]:
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
        # Match 7-40 character hex strings (Git SHAs)
        sha_pattern = r"\b([0-9a-f]{7,40})\b"
        return re.findall(sha_pattern, text, re.IGNORECASE)