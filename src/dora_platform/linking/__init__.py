"""Strict incident-to-deployment linking.

Provides R1, R2, R3 linking rules and a LinkingEngine for computing
auditable incident-deployment links per CLAUDE.md §3.2.
"""

from dora_platform.linking.engine import LinkingEngine, create_linking_engine_from_config
from dora_platform.linking.rules import (
    LinkEvidence,
    compute_links,
    rule_r1_explicit,
    rule_r2_sha_reference,
    rule_r3_time_window,
)

__all__ = [
    "LinkingEngine",
    "create_linking_engine_from_config",
    "LinkEvidence",
    "compute_links",
    "rule_r1_explicit",
    "rule_r2_sha_reference",
    "rule_r3_time_window",
]
