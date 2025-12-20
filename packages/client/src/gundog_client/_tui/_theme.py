"""Centralized theme configuration for the TUI.

This module provides a single source of truth for all styling-related
constants including colors, score thresholds, and file type mappings.

Uses the Dracula color palette: https://draculatheme.com/
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import ClassVar


class DraculaColors(str, Enum):
    """Dracula theme color palette."""

    # Core colors
    BACKGROUND = "#000000"
    FOREGROUND = "#f8f8f2"
    SELECTION = "#44475a"
    COMMENT = "#6272a4"

    # Accent colors
    CYAN = "#8be9fd"
    GREEN = "#50fa7b"
    ORANGE = "#ffb86c"
    PINK = "#ff79c6"
    PURPLE = "#bd93f9"
    RED = "#ff5555"
    YELLOW = "#f1fa8c"


@dataclass(frozen=True)
class ScoreThreshold:
    """Score threshold with associated color."""

    min_value: float
    color: str


class ScoreColors:
    """Score-based color thresholds."""

    HIGH = ScoreThreshold(min_value=0.70, color=DraculaColors.GREEN.value)
    MEDIUM = ScoreThreshold(min_value=0.40, color=DraculaColors.YELLOW.value)
    LOW = ScoreThreshold(min_value=0.0, color=DraculaColors.RED.value)

    @classmethod
    def get_color(cls, score: float) -> str:
        """Get color for a score value (0.0-1.0).

        Args:
            score: Score value between 0 and 1.

        Returns:
            Hex color string for the score.
        """
        if score >= cls.HIGH.min_value:
            return cls.HIGH.color
        elif score >= cls.MEDIUM.min_value:
            return cls.MEDIUM.color
        return cls.LOW.color


class FileTypeColors:
    """Color mapping for file types."""

    COLORS: ClassVar[dict[str, str]] = {
        "code": DraculaColors.CYAN.value,
        "docs": DraculaColors.PINK.value,
        "config": DraculaColors.ORANGE.value,
        "test": DraculaColors.GREEN.value,
    }
    DEFAULT = DraculaColors.FOREGROUND.value

    @classmethod
    def get_color(cls, file_type: str) -> str:
        """Get color for a file type.

        Args:
            file_type: Type of file (code, docs, config, test).

        Returns:
            Hex color string for the file type.
        """
        return cls.COLORS.get(file_type, cls.DEFAULT)


# Language detection mapping (extension -> language name)
LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".jsx": "jsx",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".rb": "ruby",
    ".php": "php",
    ".sh": "bash",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".html": "html",
    ".css": "css",
    ".sql": "sql",
    ".md": "markdown",
}


def get_language_for_file(path: str) -> str:
    """Get the language identifier for syntax highlighting.

    Args:
        path: File path or name.

    Returns:
        Language identifier for the Rich Syntax highlighter.
    """
    from pathlib import Path

    ext = Path(path).suffix.lower()
    return LANGUAGE_MAP.get(ext, "text")


# Graph node colors
class GraphColors:
    """Colors for graph visualization nodes."""

    QUERY_ROOT = DraculaColors.ORANGE.value
    SELECTED_DIRECT = DraculaColors.PINK.value
    SELECTED_RELATED = DraculaColors.CYAN.value
    UNSELECTED = DraculaColors.SELECTION.value
    GUIDE = DraculaColors.SELECTION.value


# Connection state colors
class ConnectionColors:
    """Colors for connection status indicators."""

    ONLINE = DraculaColors.GREEN.value
    CONNECTING = DraculaColors.YELLOW.value
    OFFLINE = DraculaColors.RED.value
