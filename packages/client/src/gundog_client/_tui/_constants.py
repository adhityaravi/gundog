"""Configuration constants for the TUI.

This module centralizes all magic numbers and configuration values
to make the TUI behavior easy to tune and maintain.
"""

from __future__ import annotations


class SearchConfig:
    """Search-related configuration."""

    DEBOUNCE_DELAY_SECONDS: float = 0.2
    DEFAULT_TOP_K: int = 30


class ConnectionConfig:
    """Connection and retry configuration."""

    MAX_CONNECTING_RETRIES: int = 10
    RETRY_MULTIPLIER: float = 1.0
    RETRY_MIN_SECONDS: int = 1
    RETRY_MAX_SECONDS: int = 10
    MONITOR_INTERVAL_SECONDS: int = 3


class PreviewConfig:
    """File preview configuration."""

    CONTEXT_LINES_BEFORE: int = 6
    CONTEXT_LINES_AFTER: int = 5
    MAX_LINES_NO_CONTEXT: int = 100
    DEFAULT_CONTEXT_LINES: int = 10
    MARKDOWN_LINE_LIMIT: int = 200


class GraphConfig:
    """Graph visualization configuration."""

    MAX_DEPTH: int = 3


class UIConfig:
    """General UI configuration."""

    LOCAL_PATH_DISPLAY_MAX_LENGTH: int = 30
    LOCAL_PATH_TRUNCATION_PREFIX: str = "..."
