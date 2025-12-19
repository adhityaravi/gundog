"""Main TUI application for gundog.

This is a stub implementation. The full TUI will be implemented
according to the ADR-002 specification.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Footer, Header, Input, Static

from gundog_core import ClientConfig, DaemonAddress


class GundogApp(App):
    """Interactive TUI for gundog semantic search.

    This is a stub implementation that will be expanded to include:
    - Real-time search with debouncing
    - Results pane with direct and related matches
    - Graph visualization pane
    - File preview modal
    - Index switching
    """

    TITLE = "gundog"
    SUB_TITLE = "Semantic Search"

    CSS = """
    Screen {
        layout: vertical;
    }

    #search-container {
        height: 3;
        padding: 0 1;
    }

    #search-input {
        width: 100%;
    }

    #main-container {
        height: 1fr;
    }

    #results-pane {
        width: 40%;
        border: solid green;
        padding: 1;
    }

    #graph-pane {
        width: 60%;
        border: solid blue;
        padding: 1;
    }

    #status-bar {
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }

    .placeholder {
        color: $text-muted;
        text-style: italic;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("q", "quit", "Quit"),
        Binding("/", "focus_search", "Search"),
        Binding("?", "show_help", "Help"),
        Binding("tab", "cycle_focus", "Cycle Focus"),
    ]

    def __init__(
        self,
        address: DaemonAddress | None = None,
        config: ClientConfig | None = None,
    ) -> None:
        """Initialize the TUI application.

        Args:
            address: Daemon address to connect to.
            config: Client configuration.
        """
        super().__init__()
        self._address = address or DaemonAddress()
        self._config = config or ClientConfig.load()

    def compose(self) -> ComposeResult:
        """Compose the UI layout."""
        yield Header()

        with Container(id="search-container"):
            yield Input(placeholder="Search...", id="search-input")

        with Horizontal(id="main-container"):
            with Vertical(id="results-pane"):
                yield Static("Results", classes="placeholder")
                yield Static(
                    "[dim]TUI implementation in progress.[/dim]\n\n"
                    "Use [cyan]gundog query <text>[/cyan] for now.",
                    classes="placeholder",
                )

            with Vertical(id="graph-pane"):
                yield Static("Graph Visualization", classes="placeholder")
                yield Static(
                    "[dim]Graph view coming soon.[/dim]",
                    classes="placeholder",
                )

        yield Static(
            f"[dim]● connecting to {self._address.http_url}[/dim]",
            id="status-bar",
        )

        yield Footer()

    def action_focus_search(self) -> None:
        """Focus the search input."""
        self.query_one("#search-input", Input).focus()

    def action_show_help(self) -> None:
        """Show help modal."""
        self.notify("Help: Press / to search, Tab to cycle, q to quit")

    def action_cycle_focus(self) -> None:
        """Cycle focus between panes."""
        self.notify("Focus cycling not yet implemented")
