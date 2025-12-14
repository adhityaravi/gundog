"""Test version information."""

from gundog import __version__


def test_version():
    """Ensure version is defined and follows semver pattern."""
    assert __version__
    parts = __version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)
