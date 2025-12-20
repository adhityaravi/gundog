"""Help modal showing keybindings reference."""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from gundog_client._tui._theme import DraculaColors


class HelpModal(ModalScreen[None]):
    """Modal showing keybinding reference with beautiful dark theme."""

    DEFAULT_CSS = f"""
    HelpModal {{
        align: center middle;
    }}

    HelpModal .help-container {{
        width: 50;
        height: auto;
        max-height: 28;
        background: {DraculaColors.BACKGROUND.value};
        border: solid {DraculaColors.SELECTION.value};
        padding: 1 2;
    }}

    HelpModal .help-title {{
        text-align: center;
        text-style: bold;
        color: {DraculaColors.GREEN.value};
        padding-bottom: 1;
        border-bottom: solid {DraculaColors.SELECTION.value};
        margin-bottom: 1;
    }}

    HelpModal .help-section {{
        color: {DraculaColors.PINK.value};
        text-style: bold;
        padding-top: 1;
    }}

    HelpModal .help-row {{
        height: 1;
    }}

    HelpModal .key {{
        color: {DraculaColors.CYAN.value};
    }}

    HelpModal .desc {{
        color: {DraculaColors.COMMENT.value};
    }}

    HelpModal .help-footer {{
        text-align: center;
        color: {DraculaColors.COMMENT.value};
        padding-top: 1;
        border-top: solid {DraculaColors.SELECTION.value};
        margin-top: 1;
    }}
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close", show=False),
        Binding("q", "close", "Close", show=False),
        Binding("?", "close", "Close", show=False),
    ]

    def compose(self) -> ComposeResult:
        """Compose the help modal."""
        with Container(classes="help-container"):
            yield Static("KEYBINDINGS", classes="help-title")

            with Vertical():
                yield Static("NAVIGATION", classes="help-section")
                yield self._row("j / ", "Next result")
                yield self._row("k / ", "Previous result")
                yield self._row("g / G", "First / Last result")
                yield self._row("Enter", "Open in editor")

                yield Static("SEARCH", classes="help-section")
                yield self._row("/", "Focus search")
                yield self._row("Esc", "Back to search")
                yield self._row("Enter", "Execute query")

                yield Static("MANAGEMENT", classes="help-section")
                yield self._row("i", "Switch index")
                yield self._row("L", "Set local path")
                yield self._row("D", "Set daemon URL")
                yield self._row("R", "Force reconnect")
                yield self._row("?", "Toggle help")
                yield self._row("q", "Quit")

            yield Static("[dim]Esc to close[/]", classes="help-footer")

    def _row(self, key: str, description: str) -> Static:
        """Create a keybinding row."""
        return Static(
            f"[key]{key:<12}[/] [desc]{description}[/]",
            classes="help-row",
        )

    def action_close(self) -> None:
        """Close the modal."""
        self.dismiss(None)
