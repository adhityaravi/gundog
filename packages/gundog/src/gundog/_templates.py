"""Predefined ignore presets for common languages."""

from enum import Enum


class IgnorePreset(str, Enum):
    """Predefined ignore patterns for common languages."""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    RUST = "rust"
    JAVA = "java"


IGNORE_PATTERNS: dict[IgnorePreset, list[str]] = {
    IgnorePreset.PYTHON: [
        "**/__pycache__/**",
        "**/*.pyc",
        "**/.venv/**",
        "**/venv/**",
        "**/.pytest_cache/**",
        "**/.mypy_cache/**",
        "**/.ruff_cache/**",
        "**/__init__.py",
        "**/_version.py",
        "**/conftest.py",
    ],
    IgnorePreset.JAVASCRIPT: [
        "**/node_modules/**",
        "**/dist/**",
        "**/build/**",
        "**/.next/**",
        "**/coverage/**",
        "**/*.min.js",
        "**/package-lock.json",
    ],
    IgnorePreset.TYPESCRIPT: [
        "**/node_modules/**",
        "**/dist/**",
        "**/build/**",
        "**/.next/**",
        "**/coverage/**",
        "**/*.d.ts",
        "**/package-lock.json",
    ],
    IgnorePreset.GO: [
        "**/vendor/**",
        "**/*_test.go",
        "**/testdata/**",
        "**/go.sum",
    ],
    IgnorePreset.RUST: [
        "**/target/**",
        "**/Cargo.lock",
    ],
    IgnorePreset.JAVA: [
        "**/target/**",
        "**/build/**",
        "**/.gradle/**",
        "**/*.class",
    ],
}


def get_ignore_patterns(preset: IgnorePreset) -> list[str]:
    """Get ignore patterns for a preset."""
    return IGNORE_PATTERNS.get(preset, [])
