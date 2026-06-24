"""Closed taxonomy for pre-payment / post-payment page generation routing."""
from __future__ import annotations

PAGE_BUILD_TYPES: frozenset[str] = frozenset(
    {
        "landing",
        "tool",
        "form",
        "directory",
        "portfolio",
        "booking",
        "app",
        "info",
        "other",
    }
)

DEFAULT_PAGE_BUILD_TYPE: str = "landing"

VALID_CONFIDENCE: frozenset[str] = frozenset({"high", "medium", "low"})
