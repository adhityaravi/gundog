"""Command-line interface for gundog using Typer."""

import json
import os
import webbrowser
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

from gundog._config import (
    EmbeddingConfig,
    GraphConfig,
    GundogConfig,
    SourceConfig,
    StorageConfig,
)
from gundog._indexer import Indexer
from gundog._query import QueryEngine
from gundog._templates import ExclusionTemplate
from gundog._visualize import generate_query_graph

app = typer.Typer(
    name="gundog",
    help="Semantic retrieval for architectural knowledge",
    no_args_is_help=True,
)

console = Console()

DEFAULT_CONFIG_PATH = Path(".gundog/config.yaml")
DEFAULT_INDEX_PATH = Path(".gundog/index")


def expand_path(path: str | Path) -> Path:
    """Expand ~ and environment variables in path."""
    return Path(os.path.expandvars(os.path.expanduser(str(path))))


class OutputFormat(str, Enum):
    """Query output format."""

    json = "json"
    paths = "paths"
    pretty = "pretty"


def parse_source(source_str: str) -> SourceConfig:
    """Parse a source string in format 'path:type:glob' or 'path:glob' or 'path'."""
    parts = source_str.split(":")
    if len(parts) == 1:
        return SourceConfig(path=str(expand_path(parts[0])))
    elif len(parts) == 2:
        # Could be path:type or path:glob - treat as type if no glob chars
        if any(c in parts[1] for c in "*?[]"):
            return SourceConfig(path=str(expand_path(parts[0])), glob=parts[1])
        return SourceConfig(path=str(expand_path(parts[0])), type=parts[1])
    else:
        return SourceConfig(path=str(expand_path(parts[0])), type=parts[1], glob=parts[2])


def load_config_or_build(
    config: Path | None,
    sources: list[str] | None,
    index: Path | None,
    excludes: list[str] | None = None,
    exclusion_template: ExclusionTemplate | None = None,
) -> GundogConfig:
    """Load config from file or build from CLI arguments."""
    # Expand paths
    if config:
        config = expand_path(config)
    if index:
        index = expand_path(index)

    # If sources are provided via CLI, build config from args (ignore config file)
    if sources:
        if not sources:
            console.print("[red]Error:[/red] --source is required when not using a config file")
            raise typer.Exit(1)

        parsed_sources = [parse_source(s) for s in sources]
        # Apply global excludes and exclusion template to all sources
        for src in parsed_sources:
            if excludes:
                src.exclude = list(excludes)
            if exclusion_template:
                src.exclusion_template = exclusion_template

        return GundogConfig(
            sources=parsed_sources,
            embedding=EmbeddingConfig(),
            storage=StorageConfig(path=str(index or DEFAULT_INDEX_PATH)),
            graph=GraphConfig(),
        )

    # Otherwise, load from config file
    config_path = config or DEFAULT_CONFIG_PATH
    try:
        return GundogConfig.load(config_path)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Config file not found: {config_path}")
        console.print()
        console.print("Either create a config file or use CLI flags:")
        console.print("  gundog index --source './docs:adr:**/*.md' --source './src:code:**/*.py'")
        console.print("  gundog query 'search term' --index .gundog/index")
        raise typer.Exit(1) from None


def load_config_for_query(
    config: Path | None,
    index: Path | None,
) -> GundogConfig:
    """Load config for query/graph commands (no sources needed)."""
    # Expand paths
    if config:
        config = expand_path(config)
    if index:
        index = expand_path(index)

    # If index is provided via CLI, build minimal config
    if index:
        return GundogConfig(
            sources=[],
            embedding=EmbeddingConfig(),
            storage=StorageConfig(path=str(index)),
            graph=GraphConfig(),
        )

    # Otherwise, load from config file
    config_path = config or DEFAULT_CONFIG_PATH
    try:
        return GundogConfig.load(config_path)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Config file not found: {config_path}")
        console.print()
        console.print("Either create a config file or specify the index location:")
        console.print("  gundog query 'search term' --index .gundog/index")
        raise typer.Exit(1) from None


@app.command()
def index(
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to config file",
        ),
    ] = None,
    source: Annotated[
        list[str] | None,
        typer.Option(
            "--source",
            "-s",
            help="Source in format 'path:type:glob' - quote globs! (can be repeated)",
        ),
    ] = None,
    exclude: Annotated[
        list[str] | None,
        typer.Option(
            "--exclude",
            "-e",
            help="Exclude pattern (quote it!), e.g. '**/test_*' (can be repeated)",
        ),
    ] = None,
    exclusion_template: Annotated[
        ExclusionTemplate | None,
        typer.Option(
            "--exclusion-template",
            help="Predefined exclusion patterns (python, javascript, typescript, go, rust, java)",
        ),
    ] = None,
    index_path: Annotated[
        Path | None,
        typer.Option(
            "--index",
            "-i",
            help="Index storage path",
        ),
    ] = None,
    rebuild: Annotated[
        bool,
        typer.Option(
            "--rebuild",
            help="Rebuild entire index from scratch",
        ),
    ] = False,
) -> None:
    """Index sources for semantic search."""
    cfg = load_config_or_build(config, source, index_path, exclude, exclusion_template)
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


@app.command()
def query(
    query_text: Annotated[str, typer.Argument(help="Search query")],
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to config file",
        ),
    ] = None,
    index_path: Annotated[
        Path | None,
        typer.Option(
            "--index",
            "-i",
            help="Index storage path",
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
    no_expand: Annotated[
        bool,
        typer.Option(
            "--no-expand",
            help="Disable graph expansion",
        ),
    ] = False,
    expand_depth: Annotated[
        int | None,
        typer.Option(
            "--expand-depth",
            help="Override expansion depth from config",
        ),
    ] = None,
    type_filter: Annotated[
        str | None,
        typer.Option(
            "--type",
            "-t",
            help="Filter results by type (matches source type, e.g., 'code', 'docs')",
        ),
    ] = None,
    output_format: Annotated[
        OutputFormat,
        typer.Option(
            "--format",
            "-f",
            help="Output format",
        ),
    ] = OutputFormat.pretty,
    show_graph: Annotated[
        bool,
        typer.Option(
            "--graph",
            "-g",
            help="Open interactive graph of query expansion",
        ),
    ] = False,
) -> None:
    """Search for relevant files."""
    cfg = load_config_for_query(config, index_path)
    engine = QueryEngine(cfg)

    result = engine.query(
        query_text=query_text,
        top_k=top,
        expand=not no_expand,
        expand_depth=expand_depth,
        type_filter=type_filter,
    )

    # Generate query expansion graph if requested
    if show_graph:
        graph_path = Path(cfg.storage.path) / "query_graph.html"
        generate_query_graph(
            query=query_text,
            direct=result.direct,
            related=result.related,
            output_path=graph_path,
        )
        console.print(f"[dim]Graph saved to {graph_path}[/dim]")
        webbrowser.open(f"file://{graph_path.absolute()}")
        return

    if output_format == OutputFormat.json:
        console.print_json(json.dumps(engine.to_json(result)))

    elif output_format == OutputFormat.paths:
        for item in result.direct:
            console.print(item["path"])
        for item in result.related:
            console.print(item["path"])

    else:  # pretty
        console.print()

        # Build direct matches table
        type_styles = {"adr": "magenta", "code": "green", "doc": "yellow"}

        if result.direct:
            has_lines = any(item.get("lines") for item in result.direct)

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

            for i, item in enumerate(result.direct, 1):
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
        if result.related:
            tree = Tree("", guide_style="dim", hide_root=True)

            branches: dict[str, Tree] = {}
            for item in result.direct:
                path = item["path"]
                label = f"[bold]{Path(path).name}[/bold]"
                branches[path] = tree.add(label)

            for item in result.related:
                via = item["via"]
                path = item["path"]
                weight = item.get("edge_weight", 0)
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
            title=f"[bold white]{result.query}[/bold white]",
            border_style="blue",
            padding=(1, 2),
        )
        console.print(panel)


@app.command()
def serve(
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to config file"),
    ] = None,
    index_path: Annotated[
        Path | None,
        typer.Option("--index", "-i", help="Index storage path"),
    ] = None,
    host: Annotated[
        str,
        typer.Option("--host", "-h", help="Host to bind to"),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", "-p", help="Port to bind to"),
    ] = 8000,
    github: Annotated[
        str,
        typer.Option("--github", "-g", help="GitHub repo URL for links"),
    ] = "",
    title: Annotated[
        str,
        typer.Option("--title", "-t", help="Custom title for the web UI"),
    ] = "gundog",
) -> None:
    """Start web UI for interactive queries."""
    try:
        from gundog._server import run_server
    except ImportError:
        console.print("[red]Error:[/red] Install serve extras: pip install gundog[serve]")
        raise typer.Exit(1) from None

    cfg = load_config_for_query(config, index_path)
    console.print(f"[dim]Starting server at http://{host}:{port}[/dim]")
    run_server(cfg, host=host, port=port, github_base=github, title=title)


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
