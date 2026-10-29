"""GitHub API client for fetching repositories, PRs, deployments, and incidents."""

import time
from typing import Any

import httpx

from dora_platform.providers.base import ProviderClient
from dora_platform.providers.github.auth import GitHubAppAuth


class GitHubClient(ProviderClient):
    """Async GitHub API client with pagination and rate limit handling."""

    @property
    def default_base_url(self) -> str:
        return "https://api.github.com"

    def __init__(self, auth: GitHubAppAuth, base_url: str | None = None) -> None:
        super().__init__(auth, base_url)
        self.auth: GitHubAppAuth = auth

    async def get_repositories(self) -> list[dict[str, Any]]:
        """Get list of repositories accessible to the GitHub App installation."""
        repos = []
        page = 1
        per_page = 100

        while True:
            response = await self._request_with_retry(
                "GET",
                "/installation/repositories",
                params={"page": page, "per_page": per_page},
            )
            response.raise_for_status()
            data = response.json()

            page_repos = data.get("repositories", [])
            repos.extend(page_repos)

            if len(page_repos) < per_page:
                break
            page += 1

        return repos

    async def get_pull_requests(
        self,
        repo_external_id: str,
        since: str | None = None,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """Get pull requests for a repository."""
        prs = []
        page = 1

        params = {
            "state": "all",
            "sort": "updated",
            "direction": "desc",
            "per_page": per_page,
        }
        if since:
            params["since"] = since

        while True:
            params["page"] = page
            response = await self._request_with_retry(
                "GET",
                f"/repos/{repo_external_id}/pulls",
                params=params,
            )
            response.raise_for_status()
            page_prs = response.json()

            if not page_prs:
                break

            prs.extend(page_prs)

            if len(page_prs) < per_page:
                break
            page += 1

        return prs

    async def get_pull_request_commits(
        self,
        repo_external_id: str,
        pr_number: int,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """Get commits for a pull request."""
        commits = []
        page = 1

        while True:
            response = await self._request_with_retry(
                "GET",
                f"/repos/{repo_external_id}/pulls/{pr_number}/commits",
                params={"page": page, "per_page": per_page},
            )
            response.raise_for_status()
            page_commits = response.json()

            if not page_commits:
                break

            commits.extend(page_commits)

            if len(page_commits) < per_page:
                break
            page += 1

        return commits

    async def get_deployments(
        self,
        repo_external_id: str,
        since: str | None = None,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """Get deployments for a repository."""
        deployments = []
        page = 1

        params = {"per_page": per_page}
        if since:
            params["since"] = since

        while True:
            params["page"] = page
            response = await self._request_with_retry(
                "GET",
                f"/repos/{repo_external_id}/deployments",
                params=params,
            )
            response.raise_for_status()
            page_deployments = response.json()

            if not page_deployments:
                break

            deployments.extend(page_deployments)

            if len(page_deployments) < per_page:
                break
            page += 1

        return deployments

    async def get_deployment_statuses(
        self,
        repo_external_id: str,
        deployment_id: int,
    ) -> list[dict[str, Any]]:
        """Get statuses for a deployment."""
        response = await self._request_with_retry(
            "GET",
            f"/repos/{repo_external_id}/deployments/{deployment_id}/statuses",
            params={"per_page": 100},
        )
        response.raise_for_status()
        return response.json()

    async def get_incidents(
        self,
        repo_external_id: str,
        since: str | None = None,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """Get incidents (issues with incident label) for a repository."""
        incidents = []
        page = 1

        # Search for issues with incident-related labels
        params = {
            "state": "all",
            "labels": "incident,bug",
            "sort": "updated",
            "direction": "desc",
            "per_page": per_page,
        }
        if since:
            params["since"] = since

        while True:
            params["page"] = page
            response = await self._request_with_retry(
                "GET",
                f"/repos/{repo_external_id}/issues",
                params=params,
            )
            response.raise_for_status()
            page_issues = response.json()

            if not page_issues:
                break

            # Filter out pull requests (they appear in issues endpoint too)
            for issue in page_issues:
                if "pull_request" not in issue:
                    incidents.append(issue)

            if len(page_issues) < per_page:
                break
            page += 1

        return incidents

    async def get_issue_comments(
        self,
        repo_external_id: str,
        issue_number: int,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """Get comments for an issue (for R2 linking)."""
        comments = []
        page = 1

        while True:
            response = await self._request_with_retry(
                "GET",
                f"/repos/{repo_external_id}/issues/{issue_number}/comments",
                params={"page": page, "per_page": per_page},
            )
            response.raise_for_status()
            page_comments = response.json()

            if not page_comments:
                break

            comments.extend(page_comments)

            if len(page_comments) < per_page:
                break
            page += 1

        return comments

    async def get_rate_limit(self) -> dict[str, Any]:
        """Get current rate limit status."""
        response = await self._request_with_retry("GET", "/rate_limit")
        response.raise_for_status()
        return response.json()