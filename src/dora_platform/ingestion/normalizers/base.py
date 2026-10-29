"""Base normalizer for converting raw events to normalized domain models."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from dora_platform.providers.base import Mapper


@dataclass(frozen=True, slots=True)
class NormalizedResult:
    """Result of normalizing a single raw event."""

    # Entities to upsert
    pull_requests: list[dict[str, Any]]
    deployments: list[dict[str, Any]]
    incidents: list[dict[str, Any]]
    commits: list[dict[str, Any]]

    # Metadata
    event_type: str
    provider: str
    delivery_id: str
    payload_hash: str


class BaseNormalizer(ABC):
    """Abstract base for provider-specific normalizers."""

    def __init__(self, mapper: Mapper) -> None:
        self.mapper = mapper

    @property
    @abstractmethod
    def supported_event_types(self) -> set[str]:
        """Set of event types this normalizer handles."""
        pass

    @abstractmethod
    async def normalize(self, raw_event: dict[str, Any]) -> NormalizedResult | None:
        """Normalize a raw event to domain models.

        Args:
            raw_event: Raw event from raw_events table with keys:
                - event_type: provider event type
                - delivery_id: unique delivery identifier
                - payload: parsed JSON payload
                - payload_hash: SHA256 of raw payload

        Returns:
            NormalizedResult with entities to upsert, or None if event not supported
        """
        pass

    def can_handle(self, event_type: str) -> bool:
        """Check if this normalizer handles the event type."""
        return event_type in self.supported_event_types