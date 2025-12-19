"""Command-line interface for gundog.

This module provides the full gundog CLI. If gundog-client is installed,
it extends the client CLI with additional commands (index, daemon, convert-onnx).
Otherwise, it provides only the server-side commands.
"""

from __future__ import annotations

import json
import os
import signal
import sys
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from gundog._config import GundogConfig
from gundog._ssl import configure_ssl, get_ssl_error_help, is_ssl_error

# Import config from core
from gundog_core import DaemonConfig

# Try to import client CLI to extend it
try:
    from gundog_client._cli import app

    _HAS_CLIENT = True
except ImportError:
    # No client - create base app with only server commands
    app = typer.Typer(
        name="gundog",
        help="Semantic retrieval for architectural knowledge",
        no_args_is_help=True,
    )
    _HAS_CLIENT = False


console = Console()

DEFAULT_CONFIG_PATH = Path(".gundog/config.yaml")


def expand_path(path: str | Path) -> Path:
    """Expand ~ and environment variables in path."""
    return Path(os.path.expandvars(os.path.expanduser(str(path))))


class OutputFormat(str, Enum):
    """Query output format."""

    json = "json"
    paths = "paths"
    pretty = "pretty"


def load_config(config_path: Path | None, auto_bootstrap: bool = False) -> GundogConfig:
    """Load config from file, optionally bootstrapping if not found."""
    path = expand_path(config_path) if config_path else DEFAULT_CONFIG_PATH
    try:
        return GundogConfig.load(path)
    except FileNotFoundError:
        if auto_bootstrap and config_path is None:
            # Auto-create config by scanning directory
            console.print("[yellow]No config found. Creating .gundog/config.yaml...[/yellow]")
            created_path = GundogConfig.bootstrap(path)
            console.print(f"[green]Created config:[/green] {created_path}")
            console.print("[dim]Edit this file to customize what gets indexed.[/dim]")
            console.print()
            return GundogConfig.load(path)
        else:
            console.print(f"[red]Error:[/red] Config file not found: {path}")
            console.print()
            console.print("Create a config file at .gundog/config.yaml:")
            console.print("  sources:")
            console.print("    - path: ./docs")
            console.print('      glob: "**/*.md"')
            console.print("    - path: ./src")
            console.print('      glob: "**/*.py"')
            raise typer.Exit(1) from None


@app.command("convert-onnx")
def convert_onnx(
    model: Annotated[
        str,
        typer.Option(
            "--model",
            "-m",
            help="HuggingFace model identifier to convert",
        ),
    ] = "BAAI/bge-large-en-v1.5",
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output directory (default: ~/.cache/gundog/onnx/{model})",
        ),
    ] = None,
    no_verify_ssl: Annotated[
        bool,
        typer.Option(
            "--no-verify-ssl",
            help="Disable SSL certificate verification (insecure)",
        ),
    ] = False,
) -> None:
    """Convert an embedding model to ONNX format for faster inference."""
    # Configure SSL before importing HuggingFace libraries
    if no_verify_ssl:
        console.print("[yellow]Warning:[/yellow] SSL verification disabled")
    configure_ssl(no_verify=no_verify_ssl)

    from gundog._embedder_onnx import convert_to_onnx

    console.print(f"[cyan]Converting model:[/cyan] {model}")
    console.print()

    try:
        output_path = convert_to_onnx(model, output)
        console.print()
        console.print("[green]Conversion complete![/green]")
        console.print(f"  Output: {output_path}")
        console.print()
        console.print("To use ONNX embeddings, update your config:")
        console.print("  [dim]embedding:[/dim]")
        console.print(f"  [dim]  model: {model}[/dim]")
        console.print("  [dim]  backend: onnx[/dim]")
    except ImportError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print()
        console.print("Install ONNX dependencies with:")
        console.print("  [bold]pip install gundog[onnx][/bold]")
        raise typer.Exit(1) from None
    except Exception as e:
        if is_ssl_error(e):
            console.print(get_ssl_error_help())
            raise typer.Exit(1) from None
        console.print(f"[red]Error during conversion:[/red] {e}")
        raise typer.Exit(1) from None


@app.command()
def index(
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to config file (default: .gundog/config.yaml)",
        ),
    ] = None,
    rebuild: Annotated[
        bool,
        typer.Option(
            "--rebuild",
            help="Rebuild entire index from scratch",
        ),
    ] = False,
    no_verify_ssl: Annotated[
        bool,
        typer.Option(
            "--no-verify-ssl",
            help="Disable SSL certificate verification (insecure)",
        ),
    ] = False,
) -> None:
    """Index sources for semantic search.

    If no config exists, auto-creates one by scanning the current directory.
    """
    # Configure SSL before importing HuggingFace libraries
    if no_verify_ssl:
        console.print("[yellow]Warning:[/yellow] SSL verification disabled")
    configure_ssl(no_verify=no_verify_ssl)

    from gundog._indexer import Indexer

    try:
        cfg = load_config(config, auto_bootstrap=True)
        indexer = Indexer(cfg)
        summary = indexer.index(rebuild=rebuild)

        console.print()
        console.print("[green]Indexing complete![/green]")
        if summary.get("chunks_indexed", 0) > 0:
            console.print(
                f"  Files indexed: {summary['files_indexed']} ({summary['chunks_indexed']} chunks)"
            )
        else:
            console.print(f"  Files indexed: {summary['files_indexed']}")
        console.print(f"  Unchanged: {summary['files_skipped']}")
        console.print(f"  Removed: {summary['files_removed']}")
    except Exception as e:
        if is_ssl_error(e):
            console.print(get_ssl_error_help())
            raise typer.Exit(1) from None
        raise


# Only add query command if client is NOT installed
# (client provides its own query command)
if not _HAS_CLIENT:

    def _query_via_daemon(
        query_text: str,
        top_k: int,
        index_name: str | None,
    ) -> dict | None:
        """Query via daemon HTTP API. Returns None if daemon not running."""
        import httpx

        try:
            config = DaemonConfig.load()
        except FileNotFoundError:
            return None

        url = f"http://{config.daemon.host}:{config.daemon.port}/api/query"
        params = {"q": query_text, "k": top_k}
        if index_name:
            params["index"] = index_name

        headers = {}
        if config.daemon.auth.enabled and config.daemon.auth.api_key:
            headers["X-API-Key"] = config.daemon.auth.api_key

        try:
            with httpx.Client(timeout=120.0) as client:
                response = client.get(url, params=params, headers=headers)
                response.raise_for_status()
                return response.json()
        except httpx.ConnectError:
            return None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                console.print("[red]Error:[/red] Authentication failed. Check your API key.")
                raise typer.Exit(1) from None
            raise

    @app.command()
    def query(
        query_text: Annotated[str, typer.Argument(help="Search query")],
        index_name: Annotated[
            str | None,
            typer.Option(
                "--index",
                "-i",
                help="Index name (registered with daemon)",
            ),
        ] = None,
        top: Annotated[
            int,
            typer.Option(
                "--top",
                "-k",
                help="Number of direct results",
            ),
        ] = 10,
        output_format: Annotated[
            OutputFormat,
            typer.Option(
                "--format",
                "-f",
                help="Output format",
            ),
        ] = OutputFormat.pretty,
    ) -> None:
        """Search for relevant files (via daemon)."""
        # Try daemon first
        result_data = _query_via_daemon(query_text, top, index_name)

        if result_data is None:
            console.print("[red]Error:[/red] Daemon is not running.")
            console.print("Start it with: [bold]gundog daemon start[/bold]")
            raise typer.Exit(1)

        # Use dict directly with bracket notation
        query_str = result_data["query"]
        direct = result_data["direct"]
        related = result_data["related"]

        if output_format == OutputFormat.json:
            console.print_json(json.dumps(result_data))

        elif output_format == OutputFormat.paths:
            for item in direct:
                console.print(item["path"])
            for item in related:
                console.print(item["path"])

        else:  # pretty
            _print_pretty_results(query_str, direct, related)

    def _print_pretty_results(query_str: str, direct: list, related: list) -> None:
        """Print results in pretty format."""
        console.print()

        # Build direct matches table
        type_styles = {"adr": "magenta", "code": "green", "doc": "yellow"}

        if direct:
            has_lines = any(item.get("lines") for item in direct)

            table = Table(
                box=box.ROUNDED,
                border_style="bright_blue",
                header_style="bold white",
                title="[bold]Direct Matches[/bold]",
                title_style="bold cyan",
                padding=(0, 1),
                expand=True,
            )
            table.add_column("#", style="dim", width=3, justify="center")
            table.add_column("Score", style="bold cyan", width=6, justify="center")
            table.add_column("File", style="white")
            if has_lines:
                table.add_column("Lines", style="yellow", width=9, justify="center")

            for i, item in enumerate(direct, 1):
                ts = type_styles.get(item["type"], "white")
                filename = Path(item["path"]).name
                row = [
                    str(i),
                    f"{item['score']:.0%}",
                    f"[{ts}]{filename}[/{ts}]",
                ]
                if has_lines:
                    row.append(item.get("lines", ""))
                table.add_row(*row)

            left_content = table
        else:
            left_content = Text("No direct matches", style="dim")

        # Build related tree
        if related:
            tree = Tree("", guide_style="dim", hide_root=True)

            branches: dict[str, Tree] = {}
            for item in direct:
                path = item["path"]
                label = f"[bold]{Path(path).name}[/bold]"
                branches[path] = tree.add(label)

            for item in related:
                via = item["via"]
                path = item["path"]
                weight = item.get("weight", item.get("edge_weight", 0))
                filename = Path(path).name

                style = type_styles.get(item["type"], "white")
                label = f"[{style}]{filename}[/{style}] [dim]{weight:.0%}[/dim]"

                if via in branches:
                    parent = branches[via]
                else:
                    parent = tree.add(f"[dim]{Path(via).name}[/dim]")
                    branches[via] = parent

                node = parent.add(label)
                branches[path] = node

            right_content = Group(
                Text("Related", style="bold dim"),
                Text(""),
                tree,
            )
        else:
            right_content = Text("", style="dim")

        # Layout: table (wide) | tree (sidebar)
        layout = Table.grid(padding=(0, 2), expand=True)
        layout.add_column("left", ratio=2)
        layout.add_column("right", ratio=1)
        layout.add_row(left_content, right_content)

        # Wrap in panel
        panel = Panel(
            layout,
            title=f"[bold white]{query_str}[/bold white]",
            border_style="blue",
            padding=(1, 2),
        )
        console.print(panel)


# =============================================================================
# Daemon commands
# =============================================================================

daemon_app = typer.Typer(
    name="daemon",
    help="Manage the gundog daemon service",
    no_args_is_help=True,
)
app.add_typer(daemon_app, name="daemon")


def _get_pid() -> int | None:
    """Get daemon PID if running."""
    pid_path = DaemonConfig.get_pid_path()
    if not pid_path.exists():
        return None

    try:
        pid = int(pid_path.read_text().strip())
        # Check if process is actually running
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        # PID file is stale, clean it up
        pid_path.unlink(missing_ok=True)
        return None


def _write_pid(pid: int) -> None:
    """Write PID to file."""
    pid_path = DaemonConfig.get_pid_path()
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(pid))


def _remove_pid() -> None:
    """Remove PID file."""
    pid_path = DaemonConfig.get_pid_path()
    pid_path.unlink(missing_ok=True)


def _notify_daemon_reload() -> bool:
    """Tell running daemon to reload config. Returns True if successful."""
    import httpx

    try:
        config = DaemonConfig.load()
    except FileNotFoundError:
        return False

    url = f"http://{config.daemon.host}:{config.daemon.port}/api/reload"
    headers = {}
    if config.daemon.auth.enabled and config.daemon.auth.api_key:
        headers["X-API-Key"] = config.daemon.auth.api_key

    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.post(url, headers=headers)
            response.raise_for_status()
            return True
    except (httpx.ConnectError, httpx.HTTPStatusError):
        return False


@daemon_app.command("start")
def daemon_start(
    foreground: Annotated[
        bool,
        typer.Option("--foreground", "-f", help="Run in foreground (don't daemonize)"),
    ] = False,
) -> None:
    """Start the gundog daemon."""
    from gundog._daemon import run_daemon

    # Check if already running
    existing_pid = _get_pid()
    if existing_pid:
        console.print(f"[yellow]Daemon already running[/yellow] (PID {existing_pid})")
        raise typer.Exit(1)

    # Load or create config
    config, created = DaemonConfig.load_or_create()
    if created:
        console.print(f"[green]Created config:[/green] {DaemonConfig.get_config_path()}")

    if not config.indexes:
        console.print("[yellow]Warning:[/yellow] No indexes configured.")
        console.print("Add an index with: [bold]gundog daemon add <name> <path>[/bold]")

    if foreground:
        # Run in foreground
        console.print(
            f"[green]Starting daemon[/green] at http://{config.daemon.host}:{config.daemon.port}"
        )
        _write_pid(os.getpid())
        try:
            run_daemon(config)
        finally:
            _remove_pid()
    else:
        # Fork and daemonize
        pid = os.fork()
        if pid > 0:
            # Parent process
            _write_pid(pid)
            console.print(
                f"[green]Daemon started[/green] at "
                f"http://{config.daemon.host}:{config.daemon.port} (PID {pid})"
            )
            if config.daemon.serve_ui:
                console.print(
                    f"[dim]Web UI available at "
                    f"http://{config.daemon.host}:{config.daemon.port}[/dim]"
                )
            return

        # Child process - daemonize
        os.setsid()
        os.umask(0)

        # Second fork to prevent zombie processes
        pid = os.fork()
        if pid > 0:
            sys.exit(0)

        # Redirect stdio to /dev/null
        sys.stdout.flush()
        sys.stderr.flush()
        with open("/dev/null", "rb") as devnull:
            os.dup2(devnull.fileno(), sys.stdin.fileno())
        with open("/dev/null", "ab") as devnull:
            os.dup2(devnull.fileno(), sys.stdout.fileno())
            os.dup2(devnull.fileno(), sys.stderr.fileno())

        # Update PID after second fork
        _write_pid(os.getpid())

        try:
            run_daemon(config)
        finally:
            _remove_pid()


@daemon_app.command("stop")
def daemon_stop() -> None:
    """Stop the gundog daemon."""
    pid = _get_pid()
    if not pid:
        console.print("[yellow]Daemon is not running[/yellow]")
        raise typer.Exit(1)

    try:
        os.kill(pid, signal.SIGTERM)
        console.print(f"[green]Daemon stopped[/green] (PID {pid})")
        _remove_pid()
    except ProcessLookupError:
        console.print("[yellow]Daemon process not found, cleaning up PID file[/yellow]")
        _remove_pid()
    except PermissionError:
        console.print("[red]Error:[/red] Permission denied to stop daemon")
        raise typer.Exit(1) from None


@daemon_app.command("status")
def daemon_status() -> None:
    """Check daemon status."""
    pid = _get_pid()
    config_path = DaemonConfig.get_config_path()

    if pid:
        console.print(f"[green]Daemon is running[/green] (PID {pid})")
        try:
            config = DaemonConfig.load()
            console.print(f"  URL: http://{config.daemon.host}:{config.daemon.port}")
            console.print(f"  Indexes: {len(config.indexes)}")
            if config.default_index:
                console.print(f"  Default: {config.default_index}")
        except FileNotFoundError:
            pass
    else:
        console.print("[dim]Daemon is not running[/dim]")

    console.print(f"  Config: {config_path}")
    console.print(f"  PID file: {DaemonConfig.get_pid_path()}")


@daemon_app.command("add")
def daemon_add(
    name: Annotated[str, typer.Argument(help="Name for this index")],
    path: Annotated[str, typer.Argument(help="Path to .gundog directory or project root")],
) -> None:
    """Register an index with the daemon."""
    config, created = DaemonConfig.load_or_create()
    if created:
        console.print(f"[green]Created config:[/green] {DaemonConfig.get_config_path()}")

    # Resolve and validate path (ensure absolute)
    resolved = expand_path(path).resolve()
    if not resolved.exists():
        console.print(f"[red]Error:[/red] Path does not exist: {resolved}")
        raise typer.Exit(1)

    # Check for .gundog subdirectory or index
    if resolved.is_dir():
        gundog_dir = resolved / ".gundog" if resolved.name != ".gundog" else resolved
        if not gundog_dir.exists():
            console.print(f"[red]Error:[/red] No .gundog directory found at {resolved}")
            console.print("Run 'gundog index' in the project first.")
            raise typer.Exit(1)
        resolved = gundog_dir

    is_new = name not in config.indexes
    was_default = config.default_index

    config.add_index(name, str(resolved))
    config.save()

    if is_new:
        console.print(f"[green]Added index:[/green] {name} -> {resolved}")
    else:
        console.print(f"[green]Updated index:[/green] {name} -> {resolved}")

    if was_default is None and config.default_index == name:
        console.print("[dim]Set as default index[/dim]")

    # Notify running daemon to reload config
    pid = _get_pid()
    if pid:
        if _notify_daemon_reload():
            console.print("[dim]Daemon reloaded config[/dim]")
        else:
            console.print(
                "[yellow]Warning:[/yellow] Could not notify daemon. Restart may be needed."
            )


@daemon_app.command("remove")
def daemon_remove(
    name: Annotated[str, typer.Argument(help="Name of the index to remove")],
) -> None:
    """Remove an index from the daemon."""
    try:
        config = DaemonConfig.load()
    except FileNotFoundError:
        console.print("[red]Error:[/red] No config file found")
        raise typer.Exit(1) from None

    if not config.remove_index(name):
        console.print(f"[red]Error:[/red] Unknown index: {name}")
        raise typer.Exit(1)

    config.save()
    console.print(f"[green]Removed index:[/green] {name}")

    # Notify running daemon to reload config
    pid = _get_pid()
    if pid:
        if _notify_daemon_reload():
            console.print("[dim]Daemon reloaded config[/dim]")
        else:
            console.print(
                "[yellow]Warning:[/yellow] Could not notify daemon. Restart may be needed."
            )


@daemon_app.command("list")
def daemon_list() -> None:
    """List registered indexes."""
    try:
        config = DaemonConfig.load()
    except FileNotFoundError:
        console.print("[dim]No config file found[/dim]")
        console.print("Run 'gundog daemon start' to create one.")
        raise typer.Exit(1) from None

    if not config.indexes:
        console.print("[dim]No indexes registered[/dim]")
        console.print("Add one with: [bold]gundog daemon add <name> <path>[/bold]")
        return

    table = Table(box=box.ROUNDED, border_style="blue")
    table.add_column("Name", style="cyan")
    table.add_column("Path", style="white")
    table.add_column("Default", style="green", justify="center")

    for name, idx_path in config.indexes.items():
        is_default = "*" if name == config.default_index else ""
        table.add_row(name, idx_path, is_default)

    console.print(table)


@daemon_app.command("reload")
def daemon_reload() -> None:
    """Reload daemon configuration."""
    pid = _get_pid()
    if not pid:
        console.print("[yellow]Daemon is not running[/yellow]")
        raise typer.Exit(1)

    if _notify_daemon_reload():
        console.print("[green]Daemon reloaded config[/green]")
    else:
        console.print("[red]Error:[/red] Could not notify daemon")
        raise typer.Exit(1)


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
