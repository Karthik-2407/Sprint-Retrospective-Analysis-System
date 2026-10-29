"""Factory for creating provider clients, webhook verifiers, and mappers."""

from dora_platform.config import settings
from dora_platform.providers.base import ProviderClient, ProviderAuth, WebhookVerifier, Mapper
from dora_platform.providers.github.auth import GitHubAppAuth, create_github_app_auth_from_config
from dora_platform.providers.github.client import GitHubClient
from dora_platform.providers.github.webhook import GitHubWebhookVerifier
from dora_platform.providers.github.mappers import GitHubMapper
from dora_platform.providers.gitlab.auth import GitLabAuth, create_gitlab_auth_from_config
from dora_platform.providers.gitlab.client import GitLabClient
from dora_platform.providers.gitlab.webhook import GitLabWebhookVerifier
from dora_platform.providers.gitlab.mappers import GitLabMapper


def get_auth(provider: str, config: dict[str, Any]) -> ProviderAuth:
    """Create provider auth from config."""
    if provider == "github":
        return create_github_app_auth_from_config(config)
    elif provider == "gitlab":
        return create_gitlab_auth_from_config(config)
    else:
        raise ValueError(f"Unknown provider: {provider}")


def get_client(provider: str, auth: ProviderAuth) -> ProviderClient:
    """Create provider API client."""
    if provider == "github":
        return GitHubClient(auth)
    elif provider == "gitlab":
        return GitLabClient(auth)
    else:
        raise ValueError(f"Unknown provider: {provider}")


def get_webhook_verifier(provider: str) -> WebhookVerifier:
    """Create webhook verifier for provider."""
    if provider == "github":
        return GitHubWebhookVerifier()
    elif provider == "gitlab":
        return GitLabWebhookVerifier()
    else:
        raise ValueError(f"Unknown provider: {provider}")


def get_mapper(provider: str) -> Mapper:
    """Create payload mapper for provider."""
    if provider == "github":
        return GitHubMapper()
    elif provider == "gitlab":
        return GitLabMapper()
    else:
        raise ValueError(f"Unknown provider: {provider}")


async def create_provider_client(provider: str, config: dict[str, Any]) -> ProviderClient:
    """Convenience: create auth + client in one call."""
    auth = get_auth(provider, config)
    return get_client(provider, auth)