"""GitHub App authentication (JWT + installation tokens)."""

import base64
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import jwt
from cryptography.hazmat.primitives import serialization

from dora_platform.config import settings
from dora_platform.providers.base import ProviderAuth


@dataclass(frozen=True, slots=True)
class InstallationToken:
    """GitHub App installation access token."""

    token: str
    expires_at: int  # Unix timestamp


class GitHubAppAuth(ProviderAuth):
    """GitHub App authentication using JWT for app-level auth
    and installation tokens for API access.
    """

    def __init__(
        self,
        app_id: str | None = None,
        private_key_path: Path | None = None,
        installation_id: str | None = None,
    ) -> None:
        self.app_id = app_id or settings.github_app_id
        self.private_key_path = private_key_path or settings.github_app_private_key_path
        self.installation_id = installation_id

        self._private_key: str | None = None
        self._installation_token: InstallationToken | None = None

    def _load_private_key(self) -> str:
        """Load and cache the private key."""
        if self._private_key is None:
            if not self.private_key_path:
                raise ValueError("GitHub App private key path not configured")
            self._private_key = self.private_key_path.read_text()
        return self._private_key

    def _generate_app_jwt(self) -> str:
        """Generate a JWT for GitHub App authentication."""
        private_key = self._load_private_key()
        now = int(time.time())

        payload = {
            "iat": now - 60,  # Issued 60 seconds ago (clock skew tolerance)
            "exp": now + 600,  # Expires in 10 minutes (max allowed)
            "iss": self.app_id,
        }

        return jwt.encode(payload, private_key, algorithm="RS256")

    async def _get_installation_token(self) -> InstallationToken:
        """Get or refresh the installation access token."""
        # Check if we have a valid cached token
        if self._installation_token is not None:
            now = int(time.time())
            # Refresh 5 minutes before expiry
            if self._installation_token.expires_at > now + 300:
                return self._installation_token

        if not self.installation_id:
            raise ValueError("GitHub App installation_id not configured")

        # Generate app JWT
        app_jwt = self._generate_app_jwt()

        # Request installation token
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://api.github.com/app/installations/{self.installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {app_jwt}",
                    "Accept": "application/vnd.github+json",
                },
            )
            response.raise_for_status()
            data = response.json()

        token = InstallationToken(
            token=data["token"],
            expires_at=int(time.time()) + 3600,  # GitHub tokens expire in 1 hour
        )
        self._installation_token = token
        return token

    async def get_headers(self) -> dict[str, str]:
        """Get authentication headers for API requests."""
        token = await self._get_installation_token()
        return {
            "Authorization": f"Bearer {token.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def refresh_if_needed(self) -> None:
        """Refresh credentials if expired."""
        # Force token refresh by clearing cache
        self._installation_token = None
        await self._get_installation_token()

    def set_installation_id(self, installation_id: str) -> None:
        """Set the installation ID (e.g., from webhook)."""
        if self.installation_id != installation_id:
            self.installation_id = installation_id
            self._installation_token = None


async def create_github_app_auth_from_config(config: dict[str, Any]) -> GitHubAppAuth:
    """Create GitHubAppAuth from provider_connection config."""
    return GitHubAppAuth(
        app_id=config.get("app_id"),
        private_key_path=Path(config["private_key_path"]) if config.get("private_key_path") else None,
        installation_id=config.get("installation_id"),
    )