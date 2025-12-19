"""Git repository utilities."""

import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import ClassVar


@dataclass(frozen=True)
class GitInfo:
    """Git metadata for a file."""

    remote_url: str
    branch: str
    relative_path: str
    repo_root: Path

    SSH_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"git@([^:]+):([^/]+)/(.+?)(?:\.git)?$")

    @classmethod
    def from_path(cls, file_path: Path) -> "GitInfo | None":
        """Extract git info for a file. Returns None if not in a git repo."""
        file_path = file_path.resolve()

        repo_root = _get_repo_root(file_path)
        if repo_root is None:
            return None

        repo_info = _get_repo_info(repo_root)
        if repo_info is None:
            return None

        remote_url, branch = repo_info

        try:
            relative_path = file_path.relative_to(repo_root)
        except ValueError:
            return None

        return cls(
            remote_url=remote_url,
            branch=branch,
            relative_path=str(relative_path),
            repo_root=repo_root,
        )

    def to_web_url(self, start_line: int | None = None, end_line: int | None = None) -> str:
        """Build web URL for viewing this file."""
        url = f"{self.remote_url}/blob/{self.branch}/{self.relative_path}"
        if start_line is not None:
            url += build_line_anchor(self.remote_url, start_line, end_line)
        return url

    @classmethod
    def normalize_remote_url(cls, url: str) -> str | None:
        """Convert git remote URL to HTTPS web URL."""
        url = url.strip()

        match = cls.SSH_PATTERN.match(url)
        if match:
            host, user, repo = match.groups()
            return f"https://{host}/{user}/{repo}"

        if url.startswith(("https://", "http://")):
            if url.endswith(".git"):
                url = url[:-4]
            return url

        return None


@lru_cache(maxsize=128)
def _get_repo_root(path: Path) -> Path | None:
    """Find git repo root for a path."""
    try:
        cwd = path if path.is_dir() else path.parent
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


@lru_cache(maxsize=64)
def _get_repo_info(repo_root: Path) -> tuple[str, str] | None:
    """Get remote URL and branch for a repo root."""
    try:
        remote_result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if remote_result.returncode != 0:
            # No origin, try first available remote
            remotes_result = subprocess.run(
                ["git", "remote"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if remotes_result.returncode != 0 or not remotes_result.stdout.strip():
                return None

            first_remote = remotes_result.stdout.strip().split("\n")[0]
            remote_result = subprocess.run(
                ["git", "remote", "get-url", first_remote],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if remote_result.returncode != 0:
                return None

        raw_url = remote_result.stdout.strip()
        remote_url = GitInfo.normalize_remote_url(raw_url)
        if not remote_url:
            return None

        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if branch_result.returncode != 0:
            branch = "main"
        else:
            branch = branch_result.stdout.strip()
            if branch == "HEAD":
                # Detached HEAD - try to get default branch
                branch = _get_default_branch(repo_root) or "main"

        return (remote_url, branch)

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def _get_default_branch(repo_root: Path) -> str | None:
    """Get the default branch name for a repo."""
    try:
        result = subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip().split("/")[-1]
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def get_git_info(file_path: Path) -> GitInfo | None:
    """Get git info for a file."""
    return GitInfo.from_path(file_path)


def build_line_anchor(url: str, start_line: int, end_line: int | None = None) -> str:
    """Build line anchor for GitHub/GitLab URLs."""
    if "gitlab" in url.lower():
        if end_line and end_line != start_line:
            return f"#L{start_line}-{end_line}"
        return f"#L{start_line}"
    else:
        if end_line and end_line != start_line:
            return f"#L{start_line}-L{end_line}"
        return f"#L{start_line}"


def clear_cache() -> None:
    """Clear the git info cache."""
    _get_repo_root.cache_clear()
    _get_repo_info.cache_clear()
