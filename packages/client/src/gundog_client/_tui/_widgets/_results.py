"""Results pane widget for displaying search results.

Shows direct matches and graph-expanded related results.
Naming conventions match the gundog WebUI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import ListItem, ListView, Static

if TYPE_CHECKING:
    from gundog_core.types import RelatedHit, SearchHit


@dataclass
class ResultSelection:
    """Represents a selected result item."""

    path: str
    name: str = field(default="")
    is_related: bool = False
    score: float = 0.0
    hit_type: str = "code"
    start_line: int | None = None
    end_line: int | None = None
    via: str | None = None
    via_name: str | None = None

    def __post_init__(self):
        """Set name from path if not provided."""
        if not self.name:
            self.name = Path(self.path).name


class ResultItem(ListItem):
    """A single result item in the results list."""

    DEFAULT_CSS = """
    ResultItem {
        height: auto;
        padding: 0 1;
    }

    ResultItem:hover {
        background: $surface;
    }

    ResultItem.--highlight {
        background: $primary-darken-2;
    }

    ResultItem .result-name {
        color: $accent;
        text-style: bold;
    }

    ResultItem .result-meta {
        color: $text-muted;
    }

    ResultItem .score {
        color: $success;
    }

    ResultItem .type-code {
        color: $success;
    }

    ResultItem .type-docs {
        color: $secondary;
    }

    ResultItem .type-config {
        color: $warning;
    }
    """

    def __init__(
        self,
        path: str,
        score: float,
        type_: str = "code",
        lines: tuple[int, int] | None = None,
        is_related: bool = False,
        via: str | None = None,
        **kwargs,
    ) -> None:
        """Initialize a result item.

        Args:
            path: File path of the result.
            score: Similarity score (0-1).
            type_: Type of file (code, docs, config).
            lines: Line range if applicable.
            is_related: Whether this is a graph-expanded related result.
            via: For related results, the path it was found via.
        """
        super().__init__(**kwargs)
        self.path = path
        self.filename = Path(path).name  # Extract filename
        self.score = score
        self.type_ = type_
        self.lines = lines
        self.is_related = is_related
        self.via = via
        self.via_name = Path(via).name if via else None

    def compose(self) -> ComposeResult:
        """Compose the result item display."""
        # Match WebUI format
        score_str = f"{int(self.score * 100)}%"
        type_class = f"type-{self.type_}"

        lines_str = f"L{self.lines[0]}-{self.lines[1]}" if self.lines else ""

        if self.is_related and self.via_name:
            # Related result format matches WebUI: "via source_name"
            yield Static(
                f"[result-name]{self.filename}[/result-name]\n"
                f"[result-meta][score]{score_str}[/score] | "
                f"[{type_class}]{self.type_}[/{type_class}] | "
                f"via {self.via_name}[/result-meta]"
            )
        else:
            # Direct result format
            meta_parts = [
                f"[score]{score_str}[/score]",
                f"[{type_class}]{self.type_}[/{type_class}]",
            ]
            if lines_str:
                meta_parts.append(lines_str)

            yield Static(
                f"[result-name]{self.filename}[/result-name]\n"
                f"[result-meta]{' | '.join(meta_parts)}[/result-meta]"
            )

    def to_selection(self) -> ResultSelection:
        """Convert to a ResultSelection."""
        return ResultSelection(
            path=self.path,
            name=self.filename,
            is_related=self.is_related,
            score=self.score,
            hit_type=self.type_,
            start_line=self.lines[0] if self.lines else None,
            end_line=self.lines[1] if self.lines else None,
            via=self.via,
            via_name=self.via_name,
        )


class ResultsPane(Widget):
    """Left pane showing direct and related search results.

    Naming conventions match the gundog WebUI:
    - "Direct Matches (N)" for direct results
    - "Related (N)" for graph-expanded results
    """

    DEFAULT_CSS = """
    ResultsPane {
        width: 40%;
        border-right: solid $primary-darken-3;
        padding: 0;
    }

    ResultsPane > Vertical {
        height: 100%;
    }

    ResultsPane .section-header {
        height: 1;
        padding: 0 1;
        background: $surface;
        color: $text-muted;
        text-style: bold;
    }

    ResultsPane .section-header-related {
        height: 1;
        padding: 0 1;
        margin-top: 1;
        background: $surface-darken-1;
        color: $text-muted;
        text-style: bold;
    }

    ResultsPane ListView {
        height: auto;
        max-height: 100%;
        scrollbar-gutter: stable;
    }

    ResultsPane .empty-message {
        padding: 1;
        color: $text-muted;
        text-style: italic;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("enter", "select_item", "Preview", show=True),
        Binding("p", "select_item", "Preview", show=False),
        Binding("y", "copy_path", "Copy Path", show=True),
        Binding("g", "go_top", "Top", show=False),
        Binding("G", "go_bottom", "Bottom", show=False),
    ]

    class ResultSelected(Message):
        """Emitted when a result is selected."""

        def __init__(self, selection: ResultSelection) -> None:
            super().__init__()
            self.selection = selection

    class PathCopied(Message):
        """Emitted when a path is copied."""

        def __init__(self, path: str) -> None:
            super().__init__()
            self.path = path

    class ResultHighlighted(Message):
        """Emitted when a result is highlighted (cursor moved to it)."""

        def __init__(self, selection: ResultSelection | None) -> None:
            super().__init__()
            self.selection = selection

    def compose(self) -> ComposeResult:
        """Compose the results pane layout."""
        with Vertical():
            yield Static("Direct Matches", classes="section-header", id="direct-header")
            yield ListView(id="direct-list")
            yield Static("Related", classes="section-header-related", id="related-header")
            yield ListView(id="related-list")

    def set_results(
        self,
        direct: list[SearchHit],
        related: list[RelatedHit],
    ) -> None:
        """Set the results to display.

        Args:
            direct: List of direct search hits.
            related: List of related hits from graph expansion.
        """
        direct_list = self.query_one("#direct-list", ListView)
        related_list = self.query_one("#related-list", ListView)
        direct_header = self.query_one("#direct-header", Static)
        related_header = self.query_one("#related-header", Static)

        # Clear existing items
        direct_list.clear()
        related_list.clear()

        # Update direct results - match WebUI: "Direct Matches (N)"
        direct_header.update(f"Direct Matches ({len(direct)})")

        for hit in direct:
            item = ResultItem(
                path=hit.path,
                score=hit.score,
                type_=hit.type,
                lines=hit.lines,
                is_related=False,
            )
            direct_list.append(item)

        # Update related results - match WebUI: "Related (N)"
        related_header.update(f"Related ({len(related)})")

        for rel in related:
            item = ResultItem(
                path=rel.path,
                score=rel.edge_weight,
                type_=rel.type,
                is_related=True,
                via=rel.via,
            )
            related_list.append(item)

        # Focus on first result if available
        if direct:
            direct_list.index = 0

    def highlight_path(self, path: str) -> None:
        """Highlight a result by path.

        Used to sync selection when graph node is focused.

        Args:
            path: The file path to highlight.
        """
        direct_list = self.query_one("#direct-list", ListView)
        related_list = self.query_one("#related-list", ListView)

        # Clear all highlights first
        for item in direct_list.query(ResultItem):
            item.remove_class("--highlight")
        for item in related_list.query(ResultItem):
            item.remove_class("--highlight")

        # Find and highlight matching item
        for i, item in enumerate(direct_list.query(ResultItem)):
            if item.path == path:
                item.add_class("--highlight")
                direct_list.index = i
                return

        for item in related_list.query(ResultItem):
            if item.path == path:
                item.add_class("--highlight")
                return

    @on(ListView.Highlighted)
    def on_list_highlighted(self, event: ListView.Highlighted) -> None:
        """Handle list item highlight."""
        if event.item and isinstance(event.item, ResultItem):
            self.post_message(self.ResultHighlighted(event.item.to_selection()))
        else:
            self.post_message(self.ResultHighlighted(None))

    @on(ListView.Selected)
    def on_list_selected(self, event: ListView.Selected) -> None:
        """Handle list item selection."""
        if event.item and isinstance(event.item, ResultItem):
            self.post_message(self.ResultSelected(event.item.to_selection()))

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        direct_list = self.query_one("#direct-list", ListView)
        if direct_list.has_focus:
            direct_list.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        direct_list = self.query_one("#direct-list", ListView)
        if direct_list.has_focus:
            direct_list.action_cursor_up()

    def action_select_item(self) -> None:
        """Select the current item."""
        direct_list = self.query_one("#direct-list", ListView)
        if direct_list.has_focus and direct_list.highlighted_child:
            direct_list.action_select_cursor()

    def action_copy_path(self) -> None:
        """Copy the path of the current item."""
        direct_list = self.query_one("#direct-list", ListView)
        if direct_list.highlighted_child and isinstance(direct_list.highlighted_child, ResultItem):
            self.post_message(self.PathCopied(direct_list.highlighted_child.path))

    def action_go_top(self) -> None:
        """Go to the top of the list."""
        direct_list = self.query_one("#direct-list", ListView)
        if direct_list.has_focus:
            direct_list.index = 0

    def action_go_bottom(self) -> None:
        """Go to the bottom of the list."""
        direct_list = self.query_one("#direct-list", ListView)
        if direct_list.has_focus and direct_list.children:
            direct_list.index = len(direct_list.children) - 1

    def get_selected_result(self) -> ResultSelection | None:
        """Get the currently selected result."""
        direct_list = self.query_one("#direct-list", ListView)
        if direct_list.highlighted_child and isinstance(direct_list.highlighted_child, ResultItem):
            return direct_list.highlighted_child.to_selection()
        return None

    def focus_list(self) -> None:
        """Focus the direct results list."""
        self.query_one("#direct-list", ListView).focus()
