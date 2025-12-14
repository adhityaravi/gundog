"""Predefined exclusion templates for common languages."""

from enum import Enum


class ExclusionTemplate(str, Enum):
    """Predefined exclusion patterns for common languages."""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    RUST = "rust"
    JAVA = "java"


EXCLUSION_PATTERNS: dict[ExclusionTemplate, list[str]] = {
    ExclusionTemplate.PYTHON: [
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
    ExclusionTemplate.JAVASCRIPT: [
        "**/node_modules/**",
        "**/dist/**",
        "**/build/**",
        "**/.next/**",
        "**/coverage/**",
        "**/*.min.js",
        "**/package-lock.json",
    ],
    ExclusionTemplate.TYPESCRIPT: [
        "**/node_modules/**",
        "**/dist/**",
        "**/build/**",
        "**/.next/**",
        "**/coverage/**",
        "**/*.d.ts",
        "**/package-lock.json",
    ],
    ExclusionTemplate.GO: [
        "**/vendor/**",
        "**/*_test.go",
        "**/testdata/**",
        "**/go.sum",
    ],
    ExclusionTemplate.RUST: [
        "**/target/**",
        "**/Cargo.lock",
    ],
    ExclusionTemplate.JAVA: [
        "**/target/**",
        "**/build/**",
        "**/.gradle/**",
        "**/*.class",
    ],
}


def get_exclusion_patterns(template: ExclusionTemplate) -> list[str]:
    """Get exclusion patterns for a template."""
    return EXCLUSION_PATTERNS.get(template, [])
