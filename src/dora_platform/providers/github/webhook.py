"""GitHub webhook verification and event parsing."""

import hmac
import hashlib
from typing import Any

from dora_platform.config import settings
from dora_platform.providers.base import WebhookVerifier


class GitHubWebhookVerifier(WebhookVerifier):
    """GitHub webhook HMAC-SHA256 verification."""

    def __init__(self, webhook_secret: str | None = None) -> None:
        self.webhook_secret = webhook_secret or settings.github_webhook_secret

    def verify(self, payload: bytes, signature_header: str | None) -> bool:
        """Verify webhook signature using constant-time comparison.

        Args:
            payload: Raw request body bytes
            signature_header: Value of X-Hub-Signature-256 header

        Returns:
            True if signature is valid, False otherwise
        """
        if not self.webhook_secret:
            # If no secret configured, skip verification (dev only)
            return True

        if not signature_header:
            return False

        # GitHub sends: "sha256=<hash>"
        if not signature_header.startswith("sha256="):
            return False

        expected_sig = signature_header[7:]  # Remove "sha256=" prefix

        # Compute HMAC-SHA256
        mac = hmac.new(
            self.webhook_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        )
        computed_sig = mac.hexdigest()

        # Constant-time comparison
        return hmac.compare_digest(computed_sig, expected_sig)

    def parse_event_type(self, headers: dict[str, str]) -> str | None:
        """Extract event type from GitHub webhook headers.

        Args:
            headers: HTTP headers dict

        Returns:
            Event type (e.g., "pull_request", "deployment", "issues") or None
        """
        return headers.get("X-GitHub-Event")

    def parse_delivery_id(self, headers: dict[str, str]) -> str | None:
        """Extract delivery ID from GitHub webhook headers.

        Args:
            headers: HTTP headers dict

        Returns:
            Delivery ID (X-GitHub-Delivery) or None
        """
        return headers.get("X-GitHub-Delivery")

    def parse_event(self, payload: bytes, headers: dict[str, str]) -> dict[str, Any] | None:
        """Parse and validate GitHub webhook event.

        Args:
            payload: Raw request body bytes
            headers: HTTP headers dict

        Returns:
            Parsed event dict with event_type, delivery_id, and data, or None if invalid
        """
        if not self.verify(payload, headers.get("X-Hub-Signature-256")):
            return None

        import json

        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return None

        event_type = self.parse_event_type(headers)
        delivery_id = self.parse_delivery_id(headers)

        if not event_type or not delivery_id:
            return None

        return {
            "event_type": event_type,
            "delivery_id": delivery_id,
            "data": data,
            "headers": {k: v for k, v in headers.items() if k.startswith("X-GitHub-")},
        }