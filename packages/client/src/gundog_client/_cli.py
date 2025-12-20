"""CLI for gundog client - query, tui, and index listing.

This module provides the base CLI that can be used standalone (gundog-client)
or extended by the full gundog package with additional commands.
"""

from __future__ import annotations

import asyncio
import json
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from gundog_client._tui import GundogApp
from gundog_core import ClientConfig, DaemonAddress, DaemonClient
from gundog_core.errors import ConnectionError, QueryError

# Base app - can be extended by full gundog package
app = typer.Typer(
    name="gundog",
    help="Semantic retrieval for architectural knowledge",
    no_args_is_help=True,
)
console = Console()


@app.command()
def query(
    query_text: Annotated[str, typer.Argument(help="Search query")],
    top_k: Annotated[int, typer.Option("--top", "-k", help="Number of results")] = 10,
    index: Annotated[str | None, typer.Option("--index", "-i", help="Index name")] = None,
    daemon: Annotated[
        str | None,
        typer.Option("--daemon", "-d", help="Daemon URL (e.g., http://127.0.0.1:7676)"),
    ] = None,
    paths_only: Annotated[
        bool, typer.Option("--paths", help="Output only file paths, one per line")
    ] = False,
    no_expand: Annotated[
        bool, typer.Option("--no-expand", help="Disable graph expansion")
    ] = False,
) -> None:
    """Execute a semantic search query against the daemon. Outputs JSON by default."""
    config = ClientConfig.load()

    # Override with CLI args if provided
    if daemon:
        try:
            address = DaemonAddress.from_url(daemon)
        except ValueError as e:
            console.print(f"[red]Invalid daemon URL:[/red] {e}")
            raise typer.Exit(1) from None
    else:
        address = config.daemon

    asyncio.run(
        _query(
            query_text,
            top_k=top_k,
            index=index or config.default_index,
            address=address,
            paths_only=paths_only,
            expand=not no_expand,
        )
    )


async def _query(
    q: str,
    *,
    top_k: int,
    index: str | None,
    address: DaemonAddress,
    paths_only: bool,
    expand: bool,
) -> None:
    """Execute query and display results."""
    try:
        async with DaemonClient(address) as client:
            result = await client.query(q, top_k=top_k, index=index, expand=expand)

            if paths_only:
                for hit in result.direct:
                    print(hit.path)
            else:
                # Raw JSON output
                output = {
                    "direct": [
                        {
                            "path": h.path,
                            "score": h.score,
                            "type": h.type,
                            "lines": list(h.lines) if h.lines else None,
                        }
                        for h in result.direct
                    ],
                    "related": [
                        {
                            "path": r.path,
                            "via": r.via,
                            "edge_weight": r.edge_weight,
                            "depth": r.depth,
                            "type": r.type,
                        }
                        for r in result.related
                    ],
                    "timing_ms": result.timing_ms,
                }
                print(json.dumps(output, indent=2))

    except ConnectionError as e:
        console.print(f"[red]Connection error:[/red] {e}")
        console.print("\n[dim]Make sure the daemon is running: gundog daemon start[/dim]")
        raise typer.Exit(1) from None
    except QueryError as e:
        console.print(f"[red]Query error:[/red] {e}")
        raise typer.Exit(1) from None


@app.command()
def tui(
    daemon: Annotated[
        str | None,
        typer.Option("--daemon", "-d", help="Daemon URL (e.g., http://127.0.0.1:7676)"),
    ] = None,
) -> None:
    """Launch interactive TUI for exploring search results."""
    config = ClientConfig.load()

    if daemon:
        try:
            address = DaemonAddress.from_url(daemon)
        except ValueError as e:
            console.print(f"[red]Invalid daemon URL:[/red] {e}")
            raise typer.Exit(1) from None
    else:
        address = config.daemon

    tui_app = GundogApp(address=address, config=config)
    try:
        tui_app.run()
    except Exception as e:
        console.print(f"[red]TUI error:[/red] {e}")
        import traceback

        traceback.print_exc()
        raise typer.Exit(1) from None


@app.command()
def indexes(
    daemon: Annotated[
        str | None,
        typer.Option("--daemon", "-d", help="Daemon URL (e.g., http://127.0.0.1:7676)"),
    ] = None,
) -> None:
    """List available indexes on the daemon."""
    config = ClientConfig.load()

    if daemon:
        try:
            address = DaemonAddress.from_url(daemon)
        except ValueError as e:
            console.print(f"[red]Invalid daemon URL:[/red] {e}")
            raise typer.Exit(1) from None
    else:
        address = config.daemon

    asyncio.run(_list_indexes(address))


async def _list_indexes(address: DaemonAddress) -> None:
    """List indexes and display in table."""
    try:
        async with DaemonClient(address) as client:
            idxs = await client.list_indexes()

            if not idxs:
                console.print("[yellow]No indexes registered.[/yellow]")
                console.print("\n[dim]Register an index: gundog daemon add <name> <path>[/dim]")
                return

            table = Table(title="Available Indexes")
            table.add_column("Name", style="cyan")
            table.add_column("Files", style="green", justify="right")
            table.add_column("Active", style="yellow", justify="center")
            table.add_column("Path", style="dim")

            for idx in idxs:
                active = "[green]●[/green]" if idx.is_active else ""
                table.add_row(idx.name, str(idx.file_count), active, idx.path)

            console.print(table)

    except ConnectionError as e:
        console.print(f"[red]Connection error:[/red] {e}")
        console.print("\n[dim]Make sure the daemon is running: gundog daemon start[/dim]")
        raise typer.Exit(1) from None


@app.command()
def config(
    show: Annotated[bool, typer.Option("--show", help="Show current config")] = False,
    init: Annotated[bool, typer.Option("--init", help="Create default config file")] = False,
) -> None:
    """Manage client configuration."""
    if init:
        path = ClientConfig.bootstrap()
        console.print(f"[green]Created config file:[/green] {path}")
        return

    if show:
        config = ClientConfig.load()
        console.print("[bold]Client Configuration[/bold]")
        console.print(f"  Config file: {ClientConfig.get_config_path()}")
        console.print(f"  Daemon: {config.daemon.http_url}")
        console.print(f"  Default index: {config.default_index or '(daemon default)'}")
        console.print(f"  Theme: {config.tui.theme}")
        console.print(f"  Local paths: {len(config.local_paths)} configured")
        return

    # Default: show help
    console.print("Use --show to view config or --init to create default config file.")


def main() -> None:
    """Entry point for gundog CLI.

    If the full gundog package is installed, delegates to its CLI
    (which includes daemon, index commands). Otherwise uses client-only CLI.
    """
    try:
        # If server package is available, use its CLI (includes all commands)
        from gundog._cli import main as server_main

        server_main()
    except ImportError:
        # Server not installed, use client-only CLI
        app()


if __name__ == "__main__":
    main()
