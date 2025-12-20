"""Main TUI application for gundog.

A beautiful, minimal terminal interface for semantic code search.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path
from typing import Any, ClassVar

from rich.syntax import Syntax
from rich.tree import Tree
from tenacity import AsyncRetrying, RetryError, stop_after_attempt, wait_exponential
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Center, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Input, Static

from gundog_client._tui._constants import (
    ConnectionConfig,
    GraphConfig,
    PreviewConfig,
    SearchConfig,
)
from gundog_client._tui._enums import ConnectionState, PreviewMode
from gundog_client._tui._modals import InputModal
from gundog_client._tui._theme import (
    ConnectionColors,
    DraculaColors,
    FileTypeColors,
    GraphColors,
    ScoreColors,
    get_language_for_file,
)
from gundog_core import ClientConfig, DaemonAddress, DaemonClient
from gundog_core.types import GraphData, IndexInfo, RelatedHit, SearchHit

logger = logging.getLogger(__name__)


class ResultStatic(Static):
    """Static widget with result data storage."""

    def __init__(
        self,
        renderable: Any = "",
        *,
        result_index: int,
        section: str,
        hit: SearchHit | RelatedHit,
        **kwargs: Any,
    ) -> None:
        super().__init__(renderable, **kwargs)
        self.result_index = result_index
        self.section = section
        self.hit = hit


class GundogApp(App):
    """Beautiful, minimal TUI for gundog semantic search."""

    TITLE = "gundog"
    ENABLE_COMMAND_PALETTE = False
    AUTO_FOCUS = None  # Disable auto-focus on first widget
    CSS_PATH = "app.tcss"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("q", "quit", "Quit", show=False),
        Binding("escape", "escape", "Escape", show=False),
        Binding("slash", "focus_search", "/", show=False),
        Binding("question_mark", "show_help", "?", show=False),
        Binding("j", "next_result", "Next", show=False),
        Binding("k", "prev_result", "Prev", show=False),
        Binding("down", "next_result", "Next", show=False),
        Binding("up", "prev_result", "Prev", show=False),
        Binding("enter", "open_file", "Open", show=False),
        Binding("i", "switch_index", "Index", show=False),
        Binding("L", "set_local_path", "Local Path", show=False),
        Binding("D", "set_daemon", "Daemon URL", show=False),
        Binding("g", "go_top", "Top", show=False),
        Binding("G", "go_bottom", "Bottom", show=False),
        Binding("R", "force_reconnect", "Reconnect", show=False),
    ]

    # Reactive state
    selected_index: reactive[int] = reactive(0)
    connection_state: reactive[ConnectionState] = reactive(ConnectionState.CONNECTING)

    def __init__(
        self,
        address: DaemonAddress | None = None,
        config: ClientConfig | None = None,
    ) -> None:
        super().__init__()
        self._address = address or DaemonAddress()
        self._config = config or ClientConfig.load()
        self._client: DaemonClient | None = None
        self._indexes: list[IndexInfo] = []
        self._active_index: str | None = None
        self._local_path: str | None = None
        self._results: list[SearchHit] = []
        self._related_results: list[RelatedHit] = []
        self._graph_data: GraphData | None = None
        self._in_related_section: bool = False
        self._related_index: int = 0
        self._last_query: str = ""
        self._background_tasks: set[asyncio.Task] = set()
        self._search_task: asyncio.Task | None = None
        self._retry_attempt: int = 0
        self._preview_mode: PreviewMode = PreviewMode.PREVIEW
        self._index_selection: int = 0

    def _create_task(self, coro) -> asyncio.Task:
        """Create and track a background task."""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    def compose(self) -> ComposeResult:
        """Compose the UI."""
        yield Static(f"[{DraculaColors.PURPLE.value} bold]ｇｕｎｄｏｇ[/]", id="title-bar")  # noqa: RUF001

        with Horizontal(id="search-container"):
            yield Static(f"[{DraculaColors.GREEN.value}]>[/]", id="search-icon")
            yield Input(placeholder="search...", id="search-input")

        with Horizontal(id="main-content"):
            with Vertical(id="results-pane"):
                with Vertical(id="direct-section"):
                    yield Static(f"[{DraculaColors.PINK.value} bold]DIRECT[/]", id="direct-header")
                    yield VerticalScroll(
                        Static("Enter a query to search", classes="empty-results"),
                        id="direct-list",
                    )
                with Vertical(id="related-section"):
                    yield Static(
                        f"[{DraculaColors.CYAN.value} bold]RELATED[/]", id="related-header"
                    )
                    yield VerticalScroll(
                        Static("Graph-expanded results", classes="empty-results"),
                        id="related-list",
                    )

            with Vertical(id="preview-pane"):
                yield Static("Preview", id="preview-header")
                yield VerticalScroll(
                    Static("Select a result to preview"),
                    id="preview-content",
                )

            with Vertical(id="graph-pane"):
                yield Static(f"[{DraculaColors.COMMENT.value}]Graph[/]", id="graph-header")
                with VerticalScroll(id="graph-scroll"):  # noqa: SIM117
                    with Center():
                        yield Static("", id="graph-content")

        with Horizontal(id="footer-bar"):
            yield Static(
                f"[{DraculaColors.CYAN.value}]j/k[/] navigate  "
                f"[{DraculaColors.CYAN.value}]Enter[/] open  "
                f"[{DraculaColors.CYAN.value}]/[/] search  "
                f"[{DraculaColors.CYAN.value}]i[/] index  "
                f"[{DraculaColors.CYAN.value}]?[/] help  "
                f"[{DraculaColors.RED.value}]q[/] quit",
                id="help-hints",
            )
            yield Static(self._format_footer_status(), id="footer-status")

    def _format_footer_status(self) -> str:
        """Format the footer status text."""
        addr = f"{self._address.host}:{self._address.port}"
        status = self._format_connection_status()
        idx_info = self._format_index_info()
        return f"{idx_info}{status}  [{DraculaColors.COMMENT.value}]{addr}[/]"

    def _format_connection_status(self) -> str:
        """Format the connection status indicator."""
        if self.connection_state == ConnectionState.ONLINE:
            return f"[{ConnectionColors.ONLINE}]● online[/]"
        elif self.connection_state == ConnectionState.CONNECTING:
            return (
                f"[{ConnectionColors.CONNECTING}]● connecting "
                f"({self._retry_attempt}/{ConnectionConfig.MAX_CONNECTING_RETRIES})[/]"
            )
        return f"[{ConnectionColors.OFFLINE}]● offline[/]"

    def _format_index_info(self) -> str:
        """Format the active index info for the status bar."""
        if not self._active_index:
            return ""
        idx = next((i for i in self._indexes if i.name == self._active_index), None)
        if not idx:
            return ""
        return (
            f"[{DraculaColors.CYAN.value}]{self._active_index}[/] "
            f"[{DraculaColors.COMMENT.value}]({idx.file_count})[/]  "
            f"[{DraculaColors.SELECTION.value}]|[/]  "
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Connection Management
    # ─────────────────────────────────────────────────────────────────────────

    async def on_mount(self) -> None:
        """Initialize on mount."""
        self._create_task(self._connect())
        self._create_task(self._connection_monitor())

    async def _try_connect(self) -> None:
        """Single connection attempt."""
        if self._client:
            try:
                await self._client.disconnect()
            except Exception as e:
                logger.debug("Error disconnecting previous client: %s", e)
        self._client = DaemonClient(self._address)
        await self._client.connect()

    async def _connect(self) -> None:
        """Connect to daemon with tenacity retry."""
        self._retry_attempt = 0
        self.connection_state = ConnectionState.CONNECTING

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(ConnectionConfig.MAX_CONNECTING_RETRIES),
                wait=wait_exponential(
                    multiplier=ConnectionConfig.RETRY_MULTIPLIER,
                    min=ConnectionConfig.RETRY_MIN_SECONDS,
                    max=ConnectionConfig.RETRY_MAX_SECONDS,
                ),
                reraise=True,
            ):
                with attempt:
                    self._retry_attempt = attempt.retry_state.attempt_number
                    self._update_connection_status()
                    await self._try_connect()
                    self.connection_state = ConnectionState.ONLINE
                    self._retry_attempt = 0
                    await self._refresh_indexes()
                    return
        except RetryError:
            logger.warning("Connection retries exhausted, moving to offline state")
            self.connection_state = ConnectionState.OFFLINE
        except Exception as e:
            logger.error("Connection failed: %s", e)
            self.connection_state = ConnectionState.OFFLINE

    async def _connection_monitor(self) -> None:
        """Monitor connection and auto-reconnect."""
        while True:
            await asyncio.sleep(ConnectionConfig.MONITOR_INTERVAL_SECONDS)
            try:
                if self._client and self._client.is_connected:
                    await self._client.list_indexes()
                    if self.connection_state != ConnectionState.ONLINE:
                        self.connection_state = ConnectionState.ONLINE
                        self._retry_attempt = 0
                        await self._refresh_indexes()
                elif self.connection_state == ConnectionState.OFFLINE:
                    try:
                        await self._try_connect()
                        self.connection_state = ConnectionState.ONLINE
                        self._retry_attempt = 0
                        await self._refresh_indexes()
                    except Exception as e:
                        logger.debug("Background reconnect failed: %s", e)
            except Exception as e:
                logger.debug("Connection monitor ping failed: %s", e)
                if self.connection_state == ConnectionState.ONLINE:
                    self.connection_state = ConnectionState.OFFLINE

    async def _refresh_indexes(self) -> None:
        """Refresh index list."""
        if not self._client:
            return
        try:
            self._indexes = await self._client.list_indexes()
            for idx in self._indexes:
                if idx.is_active:
                    self._active_index = idx.name
                    self._local_path = self._config.get_local_path(idx.name)
                    break
            self._update_status()
        except Exception as e:
            logger.error("Failed to refresh indexes: %s", e)
            self.connection_state = ConnectionState.OFFLINE

    def _update_connection_status(self) -> None:
        """Update connection status display."""
        try:
            footer_status = self.query_one("#footer-status", Static)
            footer_status.update(self._format_footer_status())
        except Exception:
            pass  # Not mounted yet

    def watch_connection_state(self, state: ConnectionState) -> None:
        """React to connection state changes."""
        self._update_connection_status()

    def _update_status(self) -> None:
        """Update status bar."""
        self._update_connection_status()

    # ─────────────────────────────────────────────────────────────────────────
    # Search
    # ─────────────────────────────────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes with debounce."""
        if event.input.id != "search-input":
            return

        if self._search_task and not self._search_task.done():
            self._search_task.cancel()

        query = event.value.strip()
        if not query:
            self._clear_search_state()
            return

        if self.connection_state != ConnectionState.ONLINE:
            return

        self._search_task = self._create_task(self._debounced_search(query))

    def _clear_search_state(self) -> None:
        """Clear all search results and related state."""
        self._results = []
        self._related_results = []
        self._graph_data = None
        self._in_related_section = False
        self._related_index = 0
        self._render_results()
        self._update_status()
        self._clear_preview()
        self._update_graph()

    async def _debounced_search(self, query: str) -> None:
        """Execute search after debounce delay."""
        try:
            await asyncio.sleep(SearchConfig.DEBOUNCE_DELAY_SECONDS)
            self._last_query = query
            await self._execute_query(query)
        except asyncio.CancelledError:
            pass  # Search was cancelled by new input

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle immediate search on Enter."""
        if event.input.id != "search-input":
            return

        if self._search_task and not self._search_task.done():
            self._search_task.cancel()

        query = event.value.strip()
        if not query:
            return

        if self.connection_state != ConnectionState.ONLINE:
            return

        self._last_query = query
        self.set_focus(None)  # Jump to results pane
        await self._execute_query(query)

    async def _execute_query(self, query: str) -> None:
        """Execute search."""
        if not self._client:
            return

        try:
            response = await self._client.query(
                query, top_k=SearchConfig.DEFAULT_TOP_K, index=self._active_index, expand=True
            )
            self._results = list(response.direct)
            self._related_results = list(response.related)
            self._graph_data = response.graph
            self.selected_index = 0
            self._in_related_section = False
            self._related_index = 0
            self._render_results()
            self._update_status()
            self._update_preview()
            self._update_graph()
        except Exception as e:
            logger.error("Query failed: %s", e)
            self.connection_state = ConnectionState.OFFLINE
            self.notify(f"Query failed: {e}", severity="error")

    # ─────────────────────────────────────────────────────────────────────────
    # Results Rendering
    # ─────────────────────────────────────────────────────────────────────────

    def _render_results(self) -> None:
        """Render results in separate direct and related sections."""
        direct_container = self.query_one("#direct-list", VerticalScroll)
        related_container = self.query_one("#related-list", VerticalScroll)
        direct_header = self.query_one("#direct-header", Static)
        related_header = self.query_one("#related-header", Static)

        direct_container.remove_children()
        related_container.remove_children()

        self._render_direct_results(direct_container, direct_header)
        self._render_related_results(related_container, related_header)

    def _render_direct_results(self, container: VerticalScroll, header: Static) -> None:
        """Render direct match results."""
        if not self._results:
            header.update(f"[{DraculaColors.PINK.value} bold]DIRECT[/]")
            container.mount(Static("No direct matches", classes="empty-results"))
            return

        header.update(
            f"[{DraculaColors.PINK.value} bold]DIRECT[/] "
            f"[{DraculaColors.COMMENT.value}]({len(self._results)})[/]"
        )

        for i, hit in enumerate(self._results):
            markup = self._format_direct_result(hit)
            item = ResultStatic(
                markup, result_index=i, section="direct", hit=hit, classes="result-item"
            )
            if not self._in_related_section and i == self.selected_index:
                item.add_class("--selected")
            container.mount(item)

    def _render_related_results(self, container: VerticalScroll, header: Static) -> None:
        """Render related/graph-expanded results."""
        if not self._related_results:
            header.update(f"[{DraculaColors.CYAN.value} bold]RELATED[/]")
            container.mount(Static("No related matches", classes="empty-results"))
            return

        header.update(
            f"[{DraculaColors.CYAN.value} bold]RELATED[/] "
            f"[{DraculaColors.COMMENT.value}]({len(self._related_results)})[/]"
        )

        for i, hit in enumerate(self._related_results):
            markup = self._format_related_result(hit)
            item = ResultStatic(
                markup, result_index=i, section="related", hit=hit, classes="result-item"
            )
            if self._in_related_section and i == self._related_index:
                item.add_class("--selected")
            container.mount(item)

    def _format_direct_result(self, hit: SearchHit) -> str:
        """Format a direct search result for display."""
        filename = Path(hit.path).name
        dirname = str(Path(hit.path).parent)
        score_color = ScoreColors.get_color(hit.score)
        type_color = FileTypeColors.get_color(hit.type)
        score_val = int(hit.score * 100)

        lines_str = ""
        if hit.lines:
            lines_str = f"[{DraculaColors.PURPLE.value}]L{hit.lines[0]}-{hit.lines[1]}[/]"

        return (
            f"[bold {DraculaColors.FOREGROUND.value}]{filename}[/]\n"
            f"[{DraculaColors.COMMENT.value}]{dirname}[/]\n"
            f"[bold {score_color}]{score_val}%[/] [{type_color}]{hit.type}[/] {lines_str}"
        )

    def _format_related_result(self, hit: RelatedHit) -> str:
        """Format a related result for display."""
        filename = Path(hit.path).name
        dirname = str(Path(hit.path).parent)
        via_file = Path(hit.via).name
        weight_color = ScoreColors.get_color(hit.edge_weight)
        type_color = FileTypeColors.get_color(hit.type)
        weight_val = int(hit.edge_weight * 100)

        return (
            f"[bold {DraculaColors.FOREGROUND.value}]{filename}[/]\n"
            f"[{DraculaColors.COMMENT.value}]{dirname}[/]\n"
            f"[bold {weight_color}]{weight_val}%[/] [{type_color}]{hit.type}[/] "
            f"[{DraculaColors.COMMENT.value}]via {via_file}[/]"
        )

    def watch_selected_index(self, index: int) -> None:
        """Update selection highlight."""
        self._update_selection_highlight()

    def _update_selection_highlight(self) -> None:
        """Update which result is highlighted."""
        direct_container = self.query_one("#direct-list", VerticalScroll)
        related_container = self.query_one("#related-list", VerticalScroll)

        for item in direct_container.query(ResultStatic):
            if not self._in_related_section and item.result_index == self.selected_index:
                item.add_class("--selected")
                item.scroll_visible()
            else:
                item.remove_class("--selected")

        for item in related_container.query(ResultStatic):
            if self._in_related_section and item.result_index == self._related_index:
                item.add_class("--selected")
                item.scroll_visible()
            else:
                item.remove_class("--selected")

        self._update_preview()
        self._update_graph()

    # ─────────────────────────────────────────────────────────────────────────
    # Preview
    # ─────────────────────────────────────────────────────────────────────────

    def _clear_preview(self) -> None:
        """Clear the preview pane."""
        try:
            header = self.query_one("#preview-header", Static)
            container = self.query_one("#preview-content", VerticalScroll)
            header.update("Preview")
            container.remove_children()
            container.mount(Static("Select a result to preview"))
        except Exception:
            pass

    def _update_preview(self) -> None:
        """Update preview pane."""
        if self._preview_mode != PreviewMode.PREVIEW:
            return

        hit = self._get_selected_hit()
        if hit:
            self._show_preview(hit)
        else:
            self._clear_preview()

    def _get_selected_hit(self) -> SearchHit | RelatedHit | None:
        """Get the currently selected hit."""
        if self._in_related_section:
            if self._related_results and self._related_index < len(self._related_results):
                return self._related_results[self._related_index]
        else:
            if self._results and self.selected_index < len(self._results):
                return self._results[self.selected_index]
        return None

    def _show_preview(self, hit: SearchHit | RelatedHit) -> None:
        """Show file preview with syntax highlighting."""
        header = self.query_one("#preview-header", Static)
        container = self.query_one("#preview-content", VerticalScroll)
        container.remove_children()

        header.update(f"[dim]{hit.path}[/]")

        if not self._local_path:
            container.mount(
                Static(
                    f"[{DraculaColors.COMMENT.value}]Set local path with[/] "
                    f"[{DraculaColors.CYAN.value}]L[/] "
                    f"[{DraculaColors.COMMENT.value}]to preview files[/]"
                )
            )
            return

        full_path = Path(self._local_path) / hit.path
        if not full_path.exists():
            container.mount(Static(f"[{DraculaColors.RED.value}]File not found:[/] {full_path}"))
            return

        try:
            content = full_path.read_text(encoding="utf-8")
            lines = content.splitlines()

            hit_lines = getattr(hit, "lines", None)
            if hit_lines:
                start = max(0, hit_lines[0] - PreviewConfig.CONTEXT_LINES_BEFORE)
                end = min(len(lines), hit_lines[1] + PreviewConfig.CONTEXT_LINES_AFTER)
                preview_content = "\n".join(lines[start:end])
                start_line = start + 1
            else:
                preview_content = "\n".join(lines[: PreviewConfig.MAX_LINES_NO_CONTEXT])
                start_line = 1

            language = get_language_for_file(hit.path)
            syntax = Syntax(
                preview_content,
                language,
                theme="dracula",
                line_numbers=True,
                start_line=start_line,
                background_color=DraculaColors.BACKGROUND.value,
            )
            container.mount(Static(syntax))
        except Exception as e:
            logger.error("Error loading preview: %s", e)
            container.mount(Static(f"[{DraculaColors.RED.value}]Error:[/] {e}"))

    # ─────────────────────────────────────────────────────────────────────────
    # Graph Visualization
    # ─────────────────────────────────────────────────────────────────────────

    def _update_graph(self) -> None:
        """Update the graph visualization using Rich Tree."""
        try:
            graph_content = self.query_one("#graph-content", Static)
        except Exception:
            return

        if not self._results and not self._related_results:
            graph_content.update(f"[{DraculaColors.COMMENT.value}]No graph data[/]")
            return

        selected_path, is_selected_direct = self._get_selected_path_info()
        tree = Tree(f"[{GraphColors.QUERY_ROOT}]●[/]", guide_style=GraphColors.GUIDE)

        children: dict[str, list[str]] = {}
        for hit in self._related_results:
            if hit.via not in children:
                children[hit.via] = []
            if hit.path not in children[hit.via]:
                children[hit.via].append(hit.path)

        visited: set[str] = set()

        def add_children(parent_tree: Tree, parent_path: str, depth: int = 0) -> None:
            if depth > GraphConfig.MAX_DEPTH:
                return
            for child_path in children.get(parent_path, []):
                if child_path in visited:
                    continue
                visited.add(child_path)
                node_color = self._get_graph_node_color(
                    child_path, selected_path, is_selected_direct
                )
                child_tree = parent_tree.add(f"[{node_color}]●[/]")
                add_children(child_tree, child_path, depth + 1)

        for hit in self._results:
            if hit.path in visited:
                continue
            visited.add(hit.path)
            node_color = self._get_graph_node_color(hit.path, selected_path, is_selected_direct)
            direct_tree = tree.add(f"[{node_color}]●[/]")
            add_children(direct_tree, hit.path, 1)

        graph_content.update(tree)

    def _get_selected_path_info(self) -> tuple[str | None, bool]:
        """Get the currently selected file path and whether it's a direct result."""
        if self._in_related_section:
            if self._related_results and self._related_index < len(self._related_results):
                return self._related_results[self._related_index].path, False
            return None, False
        else:
            if self._results and self.selected_index < len(self._results):
                return self._results[self.selected_index].path, True
            return None, True

    def _get_graph_node_color(
        self, path: str, selected_path: str | None, is_selected_direct: bool
    ) -> str:
        """Get the color for a graph node."""
        if path == selected_path:
            return (
                GraphColors.SELECTED_DIRECT if is_selected_direct else GraphColors.SELECTED_RELATED
            )
        return GraphColors.UNSELECTED

    # ─────────────────────────────────────────────────────────────────────────
    # Navigation & Actions
    # ─────────────────────────────────────────────────────────────────────────

    def action_escape(self) -> None:
        """Handle escape key - cancel modes or blur search."""
        if self._preview_mode != PreviewMode.PREVIEW:
            self._preview_mode = PreviewMode.PREVIEW
            self._update_preview()
            return
        self.set_focus(None)

    def action_focus_search(self) -> None:
        """Focus search."""
        self.query_one("#search-input", Input).focus()

    def action_next_result(self) -> None:
        """Select next result."""
        if self._preview_mode == PreviewMode.INDEX:
            if self._index_selection < len(self._indexes) - 1:
                self._index_selection += 1
                self._show_index_list()
            return

        if self._in_related_section:
            if self._related_index < len(self._related_results) - 1:
                self._related_index += 1
                self._update_selection_highlight()
        else:
            if self.selected_index < len(self._results) - 1:
                self.selected_index += 1
            elif self._related_results:
                self._in_related_section = True
                self._related_index = 0
                self._update_selection_highlight()

    def action_prev_result(self) -> None:
        """Select previous result."""
        if self._preview_mode == PreviewMode.INDEX:
            if self._index_selection > 0:
                self._index_selection -= 1
                self._show_index_list()
            return

        if self._in_related_section:
            if self._related_index > 0:
                self._related_index -= 1
                self._update_selection_highlight()
            elif self._results:
                self._in_related_section = False
                self.selected_index = len(self._results) - 1
                self._update_selection_highlight()
        else:
            if self.selected_index > 0:
                self.selected_index -= 1

    def action_go_top(self) -> None:
        """Go to first result."""
        if self._results:
            self._in_related_section = False
            self.selected_index = 0
            self._update_selection_highlight()
        elif self._related_results:
            self._in_related_section = True
            self._related_index = 0
            self._update_selection_highlight()

    def action_go_bottom(self) -> None:
        """Go to last result."""
        if self._related_results:
            self._in_related_section = True
            self._related_index = len(self._related_results) - 1
            self._update_selection_highlight()
        elif self._results:
            self._in_related_section = False
            self.selected_index = len(self._results) - 1
            self._update_selection_highlight()

    def action_open_file(self) -> None:
        """Open selected file in editor, or select index."""
        if self._preview_mode == PreviewMode.INDEX:
            if self._indexes:
                name = self._indexes[self._index_selection].name
                if name != self._active_index:
                    self._create_task(self._switch_to_index(name))
                self._preview_mode = PreviewMode.PREVIEW
                self._update_preview()
            return

        hit = self._get_selected_hit()
        if hit:
            self._open_in_editor(hit)

    def _open_in_editor(self, hit: SearchHit | RelatedHit) -> None:
        """Open file in external editor."""
        import os
        import subprocess

        if not self._local_path:
            self.notify("Set local path first (L)", severity="warning")
            return

        full_path = Path(self._local_path) / hit.path
        if not full_path.exists():
            self.notify(f"File not found: {full_path}", severity="error")
            return

        editor = os.environ.get("EDITOR", "vi")
        args = [editor]
        hit_lines = getattr(hit, "lines", None)
        if hit_lines:
            args.append(f"+{hit_lines[0]}")
        args.append(str(full_path))

        with self.suspend():
            try:
                subprocess.run(args)
            except Exception as e:
                logger.error("Failed to open editor: %s", e)

    def action_show_help(self) -> None:
        """Show help in preview pane."""
        if self._preview_mode == PreviewMode.HELP:
            self._preview_mode = PreviewMode.PREVIEW
            self._update_preview()
            return

        self._preview_mode = PreviewMode.HELP
        header = self.query_one("#preview-header", Static)
        container = self.query_one("#preview-content", VerticalScroll)
        container.remove_children()

        header.update(f"[{DraculaColors.GREEN.value}]KEYBINDINGS[/]")

        help_text = f"""[{DraculaColors.PINK.value} bold]NAVIGATION[/]
[{DraculaColors.CYAN.value}]j / [/]        Next result
[{DraculaColors.CYAN.value}]k / [/]        Previous result
[{DraculaColors.CYAN.value}]g / G[/]        First / Last result
[{DraculaColors.CYAN.value}]Enter[/]        Open in editor

[{DraculaColors.PINK.value} bold]SEARCH[/]
[{DraculaColors.CYAN.value}]/[/]            Focus search
[{DraculaColors.CYAN.value}]Esc[/]          Back to results

[{DraculaColors.PINK.value} bold]MANAGEMENT[/]
[{DraculaColors.CYAN.value}]i[/]            Switch index
[{DraculaColors.CYAN.value}]L[/]            Set local path
[{DraculaColors.CYAN.value}]R[/]            Force reconnect
[{DraculaColors.CYAN.value}]?[/]            Toggle help
[{DraculaColors.RED.value}]q[/]            Quit

[{DraculaColors.COMMENT.value}]Press ? to close[/]"""

        container.mount(Static(help_text))

    def action_force_reconnect(self) -> None:
        """Force reconnection to daemon."""
        if self.connection_state == ConnectionState.CONNECTING:
            return
        self._create_task(self._connect())

    def action_switch_index(self) -> None:
        """Show index selection in preview pane."""
        if not self._indexes:
            self.notify("No indexes available", severity="warning")
            return

        if self._preview_mode == PreviewMode.INDEX:
            self._preview_mode = PreviewMode.PREVIEW
            self._update_preview()
            return

        self._preview_mode = PreviewMode.INDEX
        self._index_selection = 0
        self._show_index_list()

    def _show_index_list(self) -> None:
        """Render index list in preview pane."""
        header = self.query_one("#preview-header", Static)
        container = self.query_one("#preview-content", VerticalScroll)
        container.remove_children()

        header.update(f"[{DraculaColors.GREEN.value}]SELECT INDEX[/]")

        lines = []
        for i, idx in enumerate(self._indexes):
            selected = "→ " if i == self._index_selection else "  "
            active = f"[{DraculaColors.GREEN.value}]●[/] " if idx.is_active else "  "
            if i == self._index_selection:
                lines.append(
                    f"[{DraculaColors.PURPLE.value}]{selected}{active}[bold]{idx.name}[/][/]"
                )
                lines.append(
                    f"[{DraculaColors.PURPLE.value}]    {idx.file_count} files  {idx.path}[/]"
                )
            else:
                lines.append(
                    f"{selected}{active}[bold {DraculaColors.FOREGROUND.value}]{idx.name}[/]"
                )
                lines.append(
                    f"[{DraculaColors.COMMENT.value}]    {idx.file_count} files  {idx.path}[/]"
                )
            lines.append("")

        lines.append(f"[{DraculaColors.COMMENT.value}]j/k navigate  Enter select  i/Esc cancel[/]")
        container.mount(Static("\n".join(lines)))

    async def _switch_to_index(self, name: str) -> None:
        """Switch to a different index."""
        if not self._client:
            return
        try:
            if await self._client.switch_index(name):
                self._active_index = name
                await self._refresh_indexes()
                if self._last_query:
                    await self._execute_query(self._last_query)
        except Exception as e:
            logger.error("Failed to switch index: %s", e)
            self.notify(f"Error: {e}", severity="error")

    def action_set_local_path(self) -> None:
        """Set local path."""

        def on_input(path: str | None) -> None:
            if path and Path(path).is_dir():
                self._local_path = path
                if self._active_index:
                    self._config.set_local_path(self._active_index, path)
                    self._config.save()
                self._update_status()
                self._update_preview()
                self.notify(f"Local path: {path}")
            elif path:
                self.notify(f"Not a directory: {path}", severity="error")

        self.push_screen(
            InputModal(
                title="LOCAL PATH",
                description="Path to your codebase for file preview",
                placeholder="/path/to/code",
                default_value=self._local_path or "",
            ),
            on_input,
        )

    def action_set_daemon(self) -> None:
        """Set daemon URL."""

        def on_input(url: str | None) -> None:
            if url:
                try:
                    new_address = DaemonAddress.from_url(url)
                    self._address = new_address
                    self._config.set_daemon_url(url)
                    self._config.save()
                    self._create_task(self._reconnect_with_new_address())
                except ValueError as e:
                    self.notify(f"Invalid URL: {e}", severity="error")

        self.push_screen(
            InputModal(
                title="DAEMON URL",
                description="URL of the gundog daemon",
                placeholder="http://127.0.0.1:7676",
                default_value=self._address.http_url,
            ),
            on_input,
        )

    async def _reconnect_with_new_address(self) -> None:
        """Reconnect to daemon with new address."""
        if self._client:
            with contextlib.suppress(Exception):
                await self._client.disconnect()
            self._client = None
        self.connection_state = ConnectionState.CONNECTING
        await self._connect()

    async def on_unmount(self) -> None:
        """Cleanup."""
        if self._client:
            try:
                await self._client.disconnect()
            except Exception as e:
                logger.debug("Error during disconnect: %s", e)
