"""Test git utilities."""

from pathlib import Path

from gundog._git import GitInfo


def test_normalize_ssh_github():
    """Test SSH URL normalization for GitHub."""
    url = "git@github.com:user/repo.git"
    assert GitInfo.normalize_remote_url(url) == "https://github.com/user/repo"


def test_normalize_ssh_gitlab():
    """Test SSH URL normalization for GitLab."""
    url = "git@gitlab.com:group/project.git"
    assert GitInfo.normalize_remote_url(url) == "https://gitlab.com/group/project"


def test_normalize_https_with_suffix():
    """Test HTTPS URL with .git suffix."""
    url = "https://github.com/user/repo.git"
    assert GitInfo.normalize_remote_url(url) == "https://github.com/user/repo"


def test_normalize_https_without_suffix():
    """Test HTTPS URL without .git suffix."""
    url = "https://github.com/user/repo"
    assert GitInfo.normalize_remote_url(url) == "https://github.com/user/repo"


def test_normalize_ssh_no_git_suffix():
    """Test SSH URL without .git suffix."""
    url = "git@github.com:user/repo"
    assert GitInfo.normalize_remote_url(url) == "https://github.com/user/repo"


def test_normalize_unsupported_returns_none():
    """Test unsupported URL formats return None."""
    assert GitInfo.normalize_remote_url("file:///local/repo") is None
    assert GitInfo.normalize_remote_url("invalid") is None


def test_normalize_http_preserved():
    """Test HTTP URLs are preserved."""
    url = "http://internal.git/repo"
    assert GitInfo.normalize_remote_url(url) == "http://internal.git/repo"


def test_to_web_url_basic():
    """Test basic web URL generation."""
    info = GitInfo(
        remote_url="https://github.com/user/repo",
        branch="main",
        relative_path="src/module.py",
        repo_root=Path("/repo"),
    )
    assert info.to_web_url() == "https://github.com/user/repo/blob/main/src/module.py"


def test_to_web_url_with_lines_github():
    """Test GitHub URL with line numbers."""
    info = GitInfo(
        remote_url="https://github.com/user/repo",
        branch="develop",
        relative_path="src/module.py",
        repo_root=Path("/repo"),
    )
    url = info.to_web_url(start_line=10, end_line=20)
    assert url == "https://github.com/user/repo/blob/develop/src/module.py#L10-L20"


def test_to_web_url_with_lines_gitlab():
    """Test GitLab URL with line numbers (different format)."""
    info = GitInfo(
        remote_url="https://gitlab.com/group/project",
        branch="main",
        relative_path="src/module.py",
        repo_root=Path("/repo"),
    )
    url = info.to_web_url(start_line=10, end_line=20)
    assert url == "https://gitlab.com/group/project/blob/main/src/module.py#L10-20"


def test_to_web_url_single_line():
    """Test URL with same start and end line."""
    info = GitInfo(
        remote_url="https://github.com/user/repo",
        branch="main",
        relative_path="src/module.py",
        repo_root=Path("/repo"),
    )
    url = info.to_web_url(start_line=42, end_line=42)
    assert url == "https://github.com/user/repo/blob/main/src/module.py#L42"


def test_to_web_url_only_start_line():
    """Test URL with only start line."""
    info = GitInfo(
        remote_url="https://github.com/user/repo",
        branch="main",
        relative_path="src/module.py",
        repo_root=Path("/repo"),
    )
    url = info.to_web_url(start_line=10)
    assert url == "https://github.com/user/repo/blob/main/src/module.py#L10"


def test_to_web_url_branch_with_slashes():
    """Test URL with branch containing slashes."""
    info = GitInfo(
        remote_url="https://github.com/user/repo",
        branch="feature/my-branch",
        relative_path="file.py",
        repo_root=Path("/repo"),
    )
    assert info.to_web_url() == "https://github.com/user/repo/blob/feature/my-branch/file.py"
