"""GitLab webhook verification and event parsing."""

import hmac
import hashlib
from typing import Any

from dora_platform.config import settings
from dora_platform.providers.base import WebhookVerifier


class GitLabWebhookVerifier(WebhookVerifier):
    """GitLab webhook token verification."""

    def __init__(self, webhook_secret: str | None = None) -> None:
        self.webhook_secret = webhook_secret or settings.gitlab_webhook_secret

    def verify(self, payload: bytes, signature_header: str | None) -> bool:
        """Verify webhook signature using constant-time comparison.

        GitLab uses X-Gitlab-Token header with the secret token.

        Args:
            payload: Raw request body bytes
            signature_header: Value of X-Gitlab-Token header

        Returns:
            True if token matches, False otherwise
        """
        if not self.webhook_secret:
            # If no secret configured, skip verification (dev only)
            return True

        if not signature_header:
            return False

        # Constant-time comparison
        return hmac.compare_digest(signature_header, self.webhook_secret)

    def parse_event_type(self, headers: dict[str, str]) -> str | None:
        """Extract event type from GitLab webhook headers.

        Args:
            headers: HTTP headers dict

        Returns:
            Event type (e.g., "Merge Request Hook", "Deployment Hook", "Issue Hook") or None
        """
        return headers.get("X-Gitlab-Event")

    def parse_delivery_id(self, headers: dict[str, str]) -> str | None:
        """Extract delivery ID from GitLab webhook headers.

        GitLab doesn't have a standard delivery ID header.
        We'll use the event UUID from the payload if available.

        Args:
            headers: HTTP headers dict

        Returns:
            Delivery ID or None
        """
        return headers.get("X-Gitlab-Event-UUID")

    def parse_event(self, payload: bytes, headers: dict[str, str]) -> dict[str, Any] | None:
        """Parse and validate GitLab webhook event.

        Args:
            payload: Raw request body bytes
            headers: HTTP headers dict

        Returns:
            Parsed event dict with event_type, delivery_id, and data, or None if invalid
        """
        if not self.verify(payload, headers.get("X-Gitlab-Token")):
            return None

        import json

        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return None

        event_type = self.parse_event_type(headers)
        delivery_id = self.parse_delivery_id(headers) or data.get("event_uuid")

        if not event_type:
            return None

        return {
            "event_type": event_type,
            "delivery_id": delivery_id,
            "data": data,
            "headers": {k: v for k, v in headers.items() if k.startswith("X-Gitlab-")},
        }