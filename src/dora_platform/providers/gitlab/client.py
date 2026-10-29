"""GitLab API client for fetching projects, MRs, deployments, and incidents."""

from typing import Any

import httpx

from dora_platform.providers.base import ProviderClient
from dora_platform.providers.gitlab.auth import GitLabAuth


class GitLabClient(ProviderClient):
    """Async GitLab API client with pagination and rate limit handling."""

    @property
    def default_base_url(self) -> str:
        return "https://gitlab.com/api/v4"

    def __init__(self, auth: GitLabAuth, base_url: str | None = None) -> None:
        super().__init__(auth, base_url or auth.base_url)
        self.auth: GitLabAuth = auth

    async def get_repositories(self) -> list[dict[str, Any]]:
        """Get list of projects accessible to the token."""
        projects = []
        page = 1
        per_page = 100

        while True:
            response = await self._request_with_retry(
                "GET",
                "/projects",
                params={"page": page, "per_page": per_page, "membership": True},
            )
            response.raise_for_status()
            page_projects = response.json()

            if not page_projects:
                break

            projects.extend(page_projects)

            if len(page_projects) < per_page:
                break
            page += 1

        return projects

    async def get_merge_requests(
        self,
        project_external_id: str,
        since: str | None = None,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """Get merge requests for a project."""
        mrs = []
        page = 1

        params = {
            "state": "all",
            "order_by": "updated_at",
            "sort": "desc",
            "per_page": per_page,
        }
        if since:
            params["updated_after"] = since

        while True:
            params["page"] = page
            response = await self._request_with_retry(
                "GET",
                f"/projects/{project_external_id}/merge_requests",
                params=params,
            )
            response.raise_for_status()
            page_mrs = response.json()

            if not page_mrs:
                break

            mrs.extend(page_mrs)

            if len(page_mrs) < per_page:
                break
            page += 1

        return mrs

    async def get_merge_request_commits(
        self,
        project_external_id: str,
        mr_iid: int,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """Get commits for a merge request."""
        commits = []
        page = 1

        while True:
            response = await self._request_with_retry(
                "GET",
                f"/projects/{project_external_id}/merge_requests/{mr_iid}/commits",
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
        project_external_id: str,
        since: str | None = None,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """Get deployments for a project."""
        deployments = []
        page = 1

        params = {"per_page": per_page, "order_by": "created_at", "sort": "desc"}
        if since:
            params["updated_after"] = since

        while True:
            params["page"] = page
            response = await self._request_with_retry(
                "GET",
                f"/projects/{project_external_id}/deployments",
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
        project_external_id: str,
        deployment_id: int,
    ) -> list[dict[str, Any]]:
        """Get statuses for a deployment."""
        response = await self._request_with_retry(
            "GET",
            f"/projects/{project_external_id}/deployments/{deployment_id}",
        )
        response.raise_for_status()
        return [response.json()]  # GitLab returns single deployment with status

    async def get_incidents(
        self,
        project_external_id: str,
        since: str | None = None,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """Get incidents (issues with incident label/type) for a project."""
        incidents = []
        page = 1

        params = {
            "state": "all",
            "labels": "incident,bug",
            "order_by": "updated_at",
            "sort": "desc",
            "per_page": per_page,
        }
        if since:
            params["updated_after"] = since

        while True:
            params["page"] = page
            response = await self._request_with_retry(
                "GET",
                f"/projects/{project_external_id}/issues",
                params=params,
            )
            response.raise_for_status()
            page_issues = response.json()

            if not page_issues:
                break

            for issue in page_issues:
                # Filter out merge requests
                if "merge_request" not in issue:
                    incidents.append(issue)

            if len(page_issues) < per_page:
                break
            page += 1

        return incidents

    async def get_issue_notes(
        self,
        project_external_id: str,
        issue_iid: int,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """Get notes/comments for an issue (for R2 linking)."""
        notes = []
        page = 1

        while True:
            response = await self._request_with_retry(
                "GET",
                f"/projects/{project_external_id}/issues/{issue_iid}/notes",
                params={"page": page, "per_page": per_page},
            )
            response.raise_for_status()
            page_notes = response.json()

            if not page_notes:
                break

            notes.extend(page_notes)

            if len(page_notes) < per_page:
                break
            page += 1

        return notes