"""GitHub event normalizer."""

from typing import Any

from dora_platform.ingestion.normalizers.base import BaseNormalizer, NormalizedResult
from dora_platform.providers.github.mappers import GitHubMapper


class GitHubNormalizer(BaseNormalizer):
    """Normalize GitHub webhook events to domain models."""

    @property
    def supported_event_types(self) -> set[str]:
        return {
            "pull_request",
            "pull_request_review",
            "deployment",
            "deployment_status",
            "issues",
            "issue_comment",
            "push",
            "workflow_run",
            "check_run",
            "check_suite",
        }

    def __init__(self) -> None:
        super().__init__(GitHubMapper())

    async def normalize(self, raw_event: dict[str, Any]) -> NormalizedResult | None:
        """Normalize GitHub webhook event."""
        event_type = raw_event["event_type"]
        payload = raw_event["payload"]
        delivery_id = raw_event["delivery_id"]
        payload_hash = raw_event["payload_hash"]

        pull_requests = []
        deployments = []
        incidents = []
        commits = []

        # Pull Request events
        if event_type == "pull_request":
            action = payload.get("action")
            if action in ("opened", "reopened", "closed", "merged", "synchronize", "ready_for_review"):
                pr = self.mapper.map_pull_request(payload)
                if pr:
                    pull_requests.append(pr)
                # Extract commits from merged PR
                if action == "merged":
                    commits.extend(self.mapper.map_commits(payload))

        # Pull Request Review events (for review metadata)
        elif event_type == "pull_request_review":
            # Could extract review data here if needed
            pass

        # Deployment events
        elif event_type == "deployment":
            action = payload.get("action")
            if action in ("created", "queued"):
                dep = self.mapper.map_deployment(payload)
                if dep:
                    deployments.append(dep)

        elif event_type == "deployment_status":
            dep = self.mapper.map_deployment(payload)
            if dep:
                deployments.append(dep)

        # Issue events (for incidents)
        elif event_type == "issues":
            action = payload.get("action")
            if action in ("opened", "reopened", "closed", "labeled", "unlabeled"):
                incident = self.mapper.map_incident(payload)
                if incident:
                    incidents.append(incident)

        # Issue comments (for R2 linking - SHA references in comments)
        elif event_type == "issue_comment":
            action = payload.get("action")
            if action in ("created", "edited"):
                # Extract SHA references from comment body for R2 linking
                comment_body = payload.get("comment", {}).get("body", "")
                shas = self.mapper._extract_sha_from_text(comment_body)
                if shas:
                    # Could store these for later linking
                    pass

        # Push events (for commits directly to main)
        elif event_type == "push":
            commits.extend(self.mapper.map_commits(payload))

        # Workflow/CI events (optional - for deployment detection)
        elif event_type in ("workflow_run", "check_run", "check_suite"):
            # Could extract deployment info from CI/CD workflows
            pass

        return NormalizedResult(
            pull_requests=pull_requests,
            deployments=deployments,
            incidents=incidents,
            commits=commits,
            event_type=event_type,
            provider="github",
            delivery_id=delivery_id,
            payload_hash=payload_hash,
        )