"""Gundog Client - Lightweight TUI and CLI for gundog semantic search.

This package provides:
- CLI commands for querying a gundog daemon (query, indexes)
- Interactive TUI for exploring search results with graph visualization

Install this package for remote access to a gundog daemon without the
heavy ML dependencies required for indexing.
"""

from gundog_client._version import __version__

__all__ = ["__version__"]
