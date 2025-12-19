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
from rich.tree import Tree

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
    host: Annotated[str | None, typer.Option("--host", "-H", help="Daemon host")] = None,
    port: Annotated[int | None, typer.Option("--port", "-p", help="Daemon port")] = None,
    format_: Annotated[
        str, typer.Option("--format", "-f", help="Output format: pretty, json, paths")
    ] = "pretty",
    no_expand: Annotated[
        bool, typer.Option("--no-expand", help="Disable graph expansion")
    ] = False,
) -> None:
    """Execute a semantic search query against the daemon."""
    config = ClientConfig.load()

    # Override with CLI args if provided
    address = DaemonAddress(
        host=host or config.daemon.host,
        port=port or config.daemon.port,
        use_tls=config.daemon.use_tls,
    )

    asyncio.run(
        _query(
            query_text,
            top_k=top_k,
            index=index or config.default_index,
            address=address,
            format_=format_,
            expand=not no_expand,
        )
    )


async def _query(
    q: str,
    *,
    top_k: int,
    index: str | None,
    address: DaemonAddress,
    format_: str,
    expand: bool,
) -> None:
    """Execute query and display results."""
    try:
        async with DaemonClient(address) as client:
            result = await client.query(q, top_k=top_k, index=index, expand=expand)

            if format_ == "json":
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
                        }
                        for r in result.related
                    ],
                    "timing_ms": result.timing_ms,
                }
                console.print_json(json.dumps(output))

            elif format_ == "paths":
                for hit in result.direct:
                    console.print(hit.path)

            else:  # pretty
                _print_pretty_results(q, result)

    except ConnectionError as e:
        console.print(f"[red]Connection error:[/red] {e}")
        console.print("\n[dim]Make sure the daemon is running: gundog daemon start[/dim]")
        raise typer.Exit(1) from None
    except QueryError as e:
        console.print(f"[red]Query error:[/red] {e}")
        raise typer.Exit(1) from None


def _print_pretty_results(q: str, result) -> None:
    """Print results in pretty format."""
    # Direct results table
    if result.direct:
        table = Table(title=f"Results for: [cyan]{q}[/cyan]")
        table.add_column("Score", style="cyan", width=8, justify="right")
        table.add_column("Path", style="green")
        table.add_column("Type", style="yellow", width=8)
        table.add_column("Lines", width=12)

        for hit in result.direct:
            score = f"{hit.score:.1%}"
            lines = f"L{hit.lines[0]}-{hit.lines[1]}" if hit.lines else "-"
            table.add_row(score, hit.path, hit.type, lines)

        console.print(table)
    else:
        console.print("[yellow]No direct matches found.[/yellow]")

    # Related results tree
    if result.related:
        console.print()
        tree = Tree("[bold]Related via graph[/bold]")
        for related in result.related:
            branch = tree.add(f"[green]{related.path}[/green]")
            branch.add(f"[dim]via {related.via} ({related.edge_weight:.1%})[/dim]")

        console.print(tree)

    # Timing
    console.print(f"\n[dim]Query took {result.timing_ms:.1f}ms[/dim]")


@app.command()
def tui(
    host: Annotated[str | None, typer.Option("--host", "-H", help="Daemon host")] = None,
    port: Annotated[int | None, typer.Option("--port", "-p", help="Daemon port")] = None,
) -> None:
    """Launch interactive TUI for exploring search results."""
    config = ClientConfig.load()

    address = DaemonAddress(
        host=host or config.daemon.host,
        port=port or config.daemon.port,
        use_tls=config.daemon.use_tls,
    )

    try:
        from gundog_client.tui.app import GundogApp

        tui_app = GundogApp(address=address, config=config)
        tui_app.run()
    except ImportError as e:
        console.print(f"[red]TUI dependencies not available:[/red] {e}")
        console.print("\n[dim]Try: pip install gundog-client[/dim]")
        raise typer.Exit(1) from None


@app.command()
def indexes(
    host: Annotated[str | None, typer.Option("--host", "-H", help="Daemon host")] = None,
    port: Annotated[int | None, typer.Option("--port", "-p", help="Daemon port")] = None,
) -> None:
    """List available indexes on the daemon."""
    config = ClientConfig.load()

    address = DaemonAddress(
        host=host or config.daemon.host,
        port=port or config.daemon.port,
        use_tls=config.daemon.use_tls,
    )

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
    """Entry point for gundog-client."""
    app()


if __name__ == "__main__":
    main()
