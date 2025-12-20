"""Theme configuration for the TUI.

# TODO: make theme switchable at runtime. See issue #33.
To switch themes, change the imports below.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

# ─────────────────────────────────────────────────────────────────────────────
# Active Theme - change these imports to switch themes
# ─────────────────────────────────────────────────────────────────────────────
from gundog_client._tui._themes._dracula import THEME, Colors

# Re-export for convenience
__all__ = [
    "THEME",
    "Colors",
    "ConnectionColors",
    "FileTypeColors",
    "GraphColors",
    "ScoreColors",
    "get_language_for_file",
]


# ─────────────────────────────────────────────────────────────────────────────
# Theme-aware utilities
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ScoreThreshold:
    """Score threshold with associated color."""

    min_value: float
    color: str


class ScoreColors:
    """Score-based color thresholds using active theme colors."""

    HIGH = ScoreThreshold(min_value=0.70, color=Colors.SUCCESS.value)
    MEDIUM = ScoreThreshold(min_value=0.40, color=Colors.INFO.value)
    LOW = ScoreThreshold(min_value=0.0, color=Colors.ERROR.value)

    @classmethod
    def get_color(cls, score: float) -> str:
        """Get color for a score value (0.0-1.0)."""
        if score >= cls.HIGH.min_value:
            return cls.HIGH.color
        elif score >= cls.MEDIUM.min_value:
            return cls.MEDIUM.color
        return cls.LOW.color


class FileTypeColors:
    """Color mapping for file types using active theme colors."""

    COLORS: ClassVar[dict[str, str]] = {
        "code": Colors.ACCENT.value,
        "docs": Colors.SECONDARY.value,
        "config": Colors.WARNING.value,
        "test": Colors.SUCCESS.value,
    }
    DEFAULT = Colors.FOREGROUND.value

    @classmethod
    def get_color(cls, file_type: str) -> str:
        """Get color for a file type."""
        return cls.COLORS.get(file_type, cls.DEFAULT)


class GraphColors:
    """Colors for graph visualization using active theme colors."""

    QUERY_ROOT = Colors.WARNING.value
    SELECTED_DIRECT = Colors.SECONDARY.value
    SELECTED_RELATED = Colors.ACCENT.value
    UNSELECTED = Colors.SURFACE.value
    GUIDE = Colors.SURFACE.value


class ConnectionColors:
    """Colors for connection status using active theme colors."""

    ONLINE = Colors.SUCCESS.value
    CONNECTING = Colors.INFO.value
    OFFLINE = Colors.ERROR.value


# ─────────────────────────────────────────────────────────────────────────────
# Language detection (theme-agnostic)
# ─────────────────────────────────────────────────────────────────────────────

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
    """Get the language identifier for syntax highlighting."""
    ext = Path(path).suffix.lower()
    return LANGUAGE_MAP.get(ext, "text")
