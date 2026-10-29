"""Factory for creating normalizers by provider."""

from dora_platform.ingestion.normalizers.base import BaseNormalizer
from dora_platform.ingestion.normalizers.github_normalizer import GitHubNormalizer
from dora_platform.ingestion.normalizers.gitlab_normalizer import GitLabNormalizer


def get_normalizer(provider: str) -> BaseNormalizer:
    """Get normalizer for provider."""
    if provider == "github":
        return GitHubNormalizer()
    elif provider == "gitlab":
        return GitLabNormalizer()
    else:
        raise ValueError(f"Unknown provider: {provider}")


def get_normalizer_for_event(provider: str, event_type: str) -> BaseNormalizer | None:
    """Get normalizer that can handle the event type."""
    normalizer = get_normalizer(provider)
    if normalizer.can_handle(event_type):
        return normalizer
    return None