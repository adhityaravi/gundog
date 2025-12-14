"""Test exclusion templates."""

from gundog._templates import (
    EXCLUSION_PATTERNS,
    ExclusionTemplate,
    get_exclusion_patterns,
)


def test_exclusion_template_enum():
    """Test ExclusionTemplate enum values."""
    assert ExclusionTemplate.PYTHON == "python"
    assert ExclusionTemplate.JAVASCRIPT == "javascript"
    assert ExclusionTemplate.TYPESCRIPT == "typescript"
    assert ExclusionTemplate.GO == "go"
    assert ExclusionTemplate.RUST == "rust"
    assert ExclusionTemplate.JAVA == "java"


def test_exclusion_template_from_string():
    """Test creating ExclusionTemplate from string."""
    assert ExclusionTemplate("python") == ExclusionTemplate.PYTHON
    assert ExclusionTemplate("javascript") == ExclusionTemplate.JAVASCRIPT


def test_python_exclusion_patterns():
    """Test Python exclusion patterns contain expected entries."""
    patterns = EXCLUSION_PATTERNS[ExclusionTemplate.PYTHON]
    assert "**/__pycache__/**" in patterns
    assert "**/*.pyc" in patterns
    assert "**/.venv/**" in patterns


def test_javascript_exclusion_patterns():
    """Test JavaScript exclusion patterns contain expected entries."""
    patterns = EXCLUSION_PATTERNS[ExclusionTemplate.JAVASCRIPT]
    assert "**/node_modules/**" in patterns
    assert "**/dist/**" in patterns


def test_typescript_exclusion_patterns():
    """Test TypeScript exclusion patterns contain expected entries."""
    patterns = EXCLUSION_PATTERNS[ExclusionTemplate.TYPESCRIPT]
    assert "**/node_modules/**" in patterns
    assert "**/*.d.ts" in patterns


def test_go_exclusion_patterns():
    """Test Go exclusion patterns contain expected entries."""
    patterns = EXCLUSION_PATTERNS[ExclusionTemplate.GO]
    assert "**/vendor/**" in patterns
    assert "**/*_test.go" in patterns


def test_rust_exclusion_patterns():
    """Test Rust exclusion patterns contain expected entries."""
    patterns = EXCLUSION_PATTERNS[ExclusionTemplate.RUST]
    assert "**/target/**" in patterns
    assert "**/Cargo.lock" in patterns


def test_java_exclusion_patterns():
    """Test Java exclusion patterns contain expected entries."""
    patterns = EXCLUSION_PATTERNS[ExclusionTemplate.JAVA]
    assert "**/target/**" in patterns
    assert "**/.gradle/**" in patterns


def test_get_exclusion_patterns():
    """Test get_exclusion_patterns helper function."""
    patterns = get_exclusion_patterns(ExclusionTemplate.PYTHON)
    assert "**/__pycache__/**" in patterns

    patterns = get_exclusion_patterns(ExclusionTemplate.RUST)
    assert "**/target/**" in patterns


def test_all_templates_have_patterns():
    """Test all templates have associated patterns."""
    for template in ExclusionTemplate:
        patterns = EXCLUSION_PATTERNS.get(template)
        assert patterns is not None, f"Missing patterns for {template}"
        assert len(patterns) > 0, f"Empty patterns for {template}"
