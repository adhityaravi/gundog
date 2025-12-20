"""Enumerations for TUI state management.

This module provides type-safe enums for various state tracking,
replacing string-based state management.
"""

from __future__ import annotations

from enum import Enum, auto


class PreviewMode(Enum):
    """Mode for the preview pane display."""

    PREVIEW = auto()  # Show file preview
    HELP = auto()  # Show keybinding help
    INDEX = auto()  # Show index selection


class ConnectionState(Enum):
    """Connection state to the daemon."""

    ONLINE = "online"
    OFFLINE = "offline"
    CONNECTING = "connecting"


class ResultSection(Enum):
    """Which results section is currently focused."""

    DIRECT = auto()
    RELATED = auto()
