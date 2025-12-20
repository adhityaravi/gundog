"""Search input widget with debouncing.

Provides a search input that debounces user input and emits search requests.
"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.timer import Timer
from textual.widgets import Input, Static


class SearchInput(Static):
    """Search input with debouncing for semantic search.

    Emits SearchInput.Submitted when the user presses Enter or after
    a debounce delay when typing stops.
    """

    DEFAULT_CSS = """
    SearchInput {
        height: 3;
        padding: 0 1;
        background: $surface;
    }

    SearchInput > Horizontal {
        height: 100%;
        width: 100%;
    }

    SearchInput .search-label {
        width: 8;
        height: 1;
        padding: 1 0;
        color: $text-muted;
    }

    SearchInput Input {
        width: 1fr;
        border: none;
        background: transparent;
    }

    SearchInput Input:focus {
        border: none;
    }

    SearchInput .loading {
        width: 3;
        height: 1;
        padding: 1 0;
        color: $warning;
    }
    """

    is_loading: reactive[bool] = reactive(False)

    class Submitted(Message):
        """Emitted when a search should be executed."""

        def __init__(self, query: str) -> None:
            super().__init__()
            self.query = query

    def __init__(
        self,
        *,
        debounce_ms: int = 300,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the search input.

        Args:
            debounce_ms: Milliseconds to wait after typing before auto-search.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._debounce_ms = debounce_ms
        self._debounce_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        """Compose the search input layout."""
        with Horizontal():
            yield Static("Search:", classes="search-label")
            yield Input(placeholder="Ask about architecture...", id="search-input")
            yield Static("", classes="loading", id="loading-indicator")

    def on_mount(self) -> None:
        """Focus the input on mount."""
        self.query_one(Input).focus()

    @on(Input.Changed)
    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes with debouncing."""
        # Cancel any existing debounce timer
        if self._debounce_timer:
            self._debounce_timer.stop()
            self._debounce_timer = None

        # Start new debounce timer if there's input
        if event.value.strip():
            self._debounce_timer = self.set_timer(
                self._debounce_ms / 1000,
                self._submit_search,
            )

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle immediate search on Enter."""
        # Cancel debounce timer
        if self._debounce_timer:
            self._debounce_timer.stop()
            self._debounce_timer = None

        if event.value.strip():
            self.post_message(self.Submitted(event.value.strip()))

    def _submit_search(self) -> None:
        """Submit the current search query."""
        query = self.query_one(Input).value.strip()
        if query:
            self.post_message(self.Submitted(query))

    def watch_is_loading(self, loading: bool) -> None:
        """Update loading indicator."""
        indicator = self.query_one("#loading-indicator", Static)
        indicator.update("[yellow]...[/yellow]" if loading else "")

    def clear(self) -> None:
        """Clear the search input."""
        self.query_one(Input).value = ""
        if self._debounce_timer:
            self._debounce_timer.stop()
            self._debounce_timer = None

    @property
    def value(self) -> str:
        """Get the current search input value."""
        return self.query_one(Input).value

    def focus_input(self) -> None:
        """Focus the search input."""
        self.query_one(Input).focus()
