"""Shared utility functions for gundog."""

import re


def tokenize(text: str) -> list[str]:
    """
    Simple tokenization for text search.

    Converts text to lowercase and splits on non-alphanumeric characters.
    Filters out tokens shorter than 2 characters.

    Args:
        text: Input text to tokenize

    Returns:
        List of lowercase tokens
    """
    text = text.lower()
    tokens = re.split(r"[^a-z0-9_]+", text)
    return [t for t in tokens if len(t) > 1]
