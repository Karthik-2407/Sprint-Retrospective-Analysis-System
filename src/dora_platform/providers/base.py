"""Base classes and interfaces for provider integrations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """Configuration for a provider connection."""

    provider: str  # "github" | "gitlab"
    external_id: str  # Installation ID, project ID, etc.
    config: dict[str, Any]  # Provider-specific config
    credentials: dict[str, Any] | None = None  # Encrypted credentials


class ProviderAuth(ABC):
    """Abstract base for provider authentication."""

    @abstractmethod
    async def get_headers(self) -> dict[str, str]:
        """Get authentication headers for API requests."""
        pass

    @abstractmethod
    async def refresh_if_needed(self) -> None:
        """Refresh credentials if expired."""
        pass


class ProviderClient(ABC):
    """Abstract base for provider API clients."""

    def __init__(self, auth: ProviderAuth, base_url: str | None = None) -> None:
        self.auth = auth
        self.base_url = base_url
        self._client: httpx.AsyncClient | None = None

    @property
    @abstractmethod
    def default_base_url(self) -> str:
        """Default base URL for the provider API."""
        pass

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url or self.default_base_url,
                timeout=httpx.Timeout(30.0, connect=10.0),
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @abstractmethod
    async def get_repositories(self) -> list[dict[str, Any]]:
        """Get list of accessible repositories."""
        pass

    @abstractmethod
    async def get_pull_requests(
        self,
        repo_external_id: str,
        since: str | None = None,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """Get pull/merge requests for a repository."""
        pass

    @abstractmethod
    async def get_deployments(
        self,
        repo_external_id: str,
        since: str | None = None,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """Get deployments for a repository."""
        pass

    @abstractmethod
    async def get_incidents(
        self,
        repo_external_id: str,
        since: str | None = None,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """Get incidents/issues for a repository."""
        pass

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make HTTP request with retry logic for rate limits."""
        client = await self._get_client()
        headers = await self.auth.get_headers()
        request_headers = {**headers, **kwargs.pop("headers", {})}

        max_retries = 3
        for attempt in range(max_retries):
            response = await client.request(method, url, headers=request_headers, **kwargs)

            if response.status_code == 403:
                # Check for rate limit
                reset_at = response.headers.get("X-RateLimit-Reset")
                if reset_at:
                    import asyncio
                    import time

                    wait_time = max(0, int(reset_at) - int(time.time())) + 1
                    wait_time = min(wait_time, 60)  # Cap at 60 seconds
                    await asyncio.sleep(wait_time)
                    continue

            if response.status_code == 429:
                # Rate limited - use Retry-After header
                retry_after = response.headers.get("Retry-After")
                import asyncio

                wait_time = int(retry_after) if retry_after else (2 ** attempt)
                wait_time = min(wait_time, 60)
                await asyncio.sleep(wait_time)
                continue

            return response

        return response


class WebhookVerifier(ABC):
    """Abstract base for webhook signature verification."""

    @abstractmethod
    def verify(self, payload: bytes, signature_header: str | None) -> bool:
        """Verify webhook signature. Returns True if valid."""
        pass

    @abstractmethod
    def parse_event_type(self, headers: dict[str, str]) -> str | None:
        """Extract event type from webhook headers."""
        pass

    @abstractmethod
    def parse_delivery_id(self, headers: dict[str, str]) -> str | None:
        """Extract delivery ID from webhook headers."""
        pass


class Mapper(ABC):
    """Abstract base for mapping provider payloads to domain models."""

    @property
    @abstractmethod
    def provider(self) -> str:
        """Provider name: 'github' or 'gitlab'."""
        pass

    @abstractmethod
    def map_pull_request(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Map provider PR/MR payload to normalized PR dict."""
        pass

    @abstractmethod
    def map_deployment(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Map provider deployment payload to normalized deployment dict."""
        pass

    @abstractmethod
    def map_incident(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Map provider incident/issue payload to normalized incident dict."""
        pass

    @abstractmethod
    def map_commits(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract commits from payload (PR merge, deployment, etc.)."""
        pass