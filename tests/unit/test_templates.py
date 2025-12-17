"""Test ignore presets."""

from gundog._templates import (
    IGNORE_PATTERNS,
    IgnorePreset,
    get_ignore_patterns,
)


def test_ignore_preset_enum():
    """Test IgnorePreset enum values."""
    assert IgnorePreset.PYTHON == "python"
    assert IgnorePreset.JAVASCRIPT == "javascript"
    assert IgnorePreset.TYPESCRIPT == "typescript"
    assert IgnorePreset.GO == "go"
    assert IgnorePreset.RUST == "rust"
    assert IgnorePreset.JAVA == "java"


def test_ignore_preset_from_string():
    """Test creating IgnorePreset from string."""
    assert IgnorePreset("python") == IgnorePreset.PYTHON
    assert IgnorePreset("javascript") == IgnorePreset.JAVASCRIPT


def test_python_ignore_patterns():
    """Test Python ignore patterns contain expected entries."""
    patterns = IGNORE_PATTERNS[IgnorePreset.PYTHON]
    assert "**/__pycache__/**" in patterns
    assert "**/*.pyc" in patterns
    assert "**/.venv/**" in patterns


def test_javascript_ignore_patterns():
    """Test JavaScript ignore patterns contain expected entries."""
    patterns = IGNORE_PATTERNS[IgnorePreset.JAVASCRIPT]
    assert "**/node_modules/**" in patterns
    assert "**/dist/**" in patterns


def test_typescript_ignore_patterns():
    """Test TypeScript ignore patterns contain expected entries."""
    patterns = IGNORE_PATTERNS[IgnorePreset.TYPESCRIPT]
    assert "**/node_modules/**" in patterns
    assert "**/*.d.ts" in patterns


def test_go_ignore_patterns():
    """Test Go ignore patterns contain expected entries."""
    patterns = IGNORE_PATTERNS[IgnorePreset.GO]
    assert "**/vendor/**" in patterns
    assert "**/*_test.go" in patterns


def test_rust_ignore_patterns():
    """Test Rust ignore patterns contain expected entries."""
    patterns = IGNORE_PATTERNS[IgnorePreset.RUST]
    assert "**/target/**" in patterns
    assert "**/Cargo.lock" in patterns


def test_java_ignore_patterns():
    """Test Java ignore patterns contain expected entries."""
    patterns = IGNORE_PATTERNS[IgnorePreset.JAVA]
    assert "**/target/**" in patterns
    assert "**/.gradle/**" in patterns


def test_get_ignore_patterns():
    """Test get_ignore_patterns helper function."""
    patterns = get_ignore_patterns(IgnorePreset.PYTHON)
    assert "**/__pycache__/**" in patterns

    patterns = get_ignore_patterns(IgnorePreset.RUST)
    assert "**/target/**" in patterns


def test_all_presets_have_patterns():
    """Test all presets have associated patterns."""
    for preset in IgnorePreset:
        patterns = IGNORE_PATTERNS.get(preset)
        assert patterns is not None, f"Missing patterns for {preset}"
        assert len(patterns) > 0, f"Empty patterns for {preset}"
