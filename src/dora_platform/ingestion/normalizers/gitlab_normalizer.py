"""GitLab event normalizer."""

from typing import Any

from dora_platform.ingestion.normalizers.base import BaseNormalizer, NormalizedResult
from dora_platform.providers.gitlab.mappers import GitLabMapper


class GitLabNormalizer(BaseNormalizer):
    """Normalize GitLab webhook events to domain models."""

    @property
    def supported_event_types(self) -> set[str]:
        return {
            "Merge Request Hook",
            "Deployment Hook",
            "Issue Hook",
            "Note Hook",
            "Push Hook",
            "Pipeline Hook",
            "Job Hook",
        }

    def __init__(self) -> None:
        super().__init__(GitLabMapper())

    async def normalize(self, raw_event: dict[str, Any]) -> NormalizedResult | None:
        """Normalize GitLab webhook event."""
        event_type = raw_event["event_type"]
        payload = raw_event["payload"]
        delivery_id = raw_event["delivery_id"]
        payload_hash = raw_event["payload_hash"]

        pull_requests = []
        deployments = []
        incidents = []
        commits = []

        # Merge Request events
        if event_type == "Merge Request Hook":
            action = payload.get("object_attributes", {}).get("action")
            if action in ("open", "reopen", "close", "merge", "update", "approved", "unapproved"):
                mr = self.mapper.map_pull_request(payload)
                if mr:
                    pull_requests.append(mr)
                # Extract commits from merged MR
                if action == "merge":
                    commits.extend(self.mapper.map_commits(payload))

        # Deployment events
        elif event_type == "Deployment Hook":
            action = payload.get("object_attributes", {}).get("status")
            if action in ("created", "running", "success", "failed", "canceled"):
                dep = self.mapper.map_deployment(payload)
                if dep:
                    deployments.append(dep)

        # Issue events (for incidents)
        elif event_type == "Issue Hook":
            action = payload.get("object_attributes", {}).get("action")
            if action in ("open", "reopen", "close", "update"):
                incident = self.mapper.map_incident(payload)
                if incident:
                    incidents.append(incident)

        # Note/Comment events (for R2 linking)
        elif event_type == "Note Hook":
            note = payload.get("object_attributes", {})
            if note.get("noteable_type") in ("Issue", "MergeRequest"):
                note_body = note.get("note", "")
                shas = self.mapper._extract_sha_from_text(note_body)
                if shas:
                    # Could store these for later linking
                    pass

        # Push events
        elif event_type == "Push Hook":
            commits.extend(self.mapper.map_commits(payload))

        # Pipeline/Job events (optional - for deployment detection)
        elif event_type in ("Pipeline Hook", "Job Hook"):
            # Could extract deployment info from CI/CD pipelines
            pass

        return NormalizedResult(
            pull_requests=pull_requests,
            deployments=deployments,
            incidents=incidents,
            commits=commits,
            event_type=event_type,
            provider="gitlab",
            delivery_id=delivery_id,
            payload_hash=payload_hash,
        )