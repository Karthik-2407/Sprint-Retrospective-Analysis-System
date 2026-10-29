"""GitLab authentication (Personal/Project/Group Access Tokens)."""

from dataclasses import dataclass
from typing import Any

import httpx

from dora_platform.config import settings
from dora_platform.providers.base import ProviderAuth


@dataclass(frozen=True, slots=True)
class GitLabToken:
    """GitLab access token."""

    token: str
    expires_at: int | None = None  # Unix timestamp, None = no expiry


class GitLabAuth(ProviderAuth):
    """GitLab authentication using Personal/Project/Group Access Tokens."""

    def __init__(
        self,
        token: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.token = token or settings.gitlab_access_token
        self.base_url = base_url or settings.gitlab_base_url or "https://gitlab.com"

    async def get_headers(self) -> dict[str, str]:
        """Get authentication headers for API requests."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

    async def refresh_if_needed(self) -> None:
        """Refresh credentials if expired.

        GitLab PATs don't auto-refresh. This is a no-op unless
        using OAuth tokens with refresh logic.
        """
        pass


async def create_gitlab_auth_from_config(config: dict[str, Any]) -> GitLabAuth:
    """Create GitLabAuth from provider_connection config."""
    return GitLabAuth(
        token=config.get("access_token"),
        base_url=config.get("base_url"),
    )