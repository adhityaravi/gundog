"""Input modal for text entry."""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from gundog_client._tui._theme import DraculaColors


class InputModal(ModalScreen[str | None]):
    """Modal for single-line text input."""

    DEFAULT_CSS = f"""
    InputModal {{
        align: center middle;
    }}

    InputModal .input-container {{
        width: 60;
        height: auto;
        background: {DraculaColors.BACKGROUND.value};
        border: solid {DraculaColors.SELECTION.value};
        padding: 1 2;
    }}

    InputModal .input-title {{
        text-align: center;
        text-style: bold;
        color: {DraculaColors.GREEN.value};
        padding-bottom: 1;
        border-bottom: solid {DraculaColors.SELECTION.value};
    }}

    InputModal .input-description {{
        color: {DraculaColors.COMMENT.value};
        padding: 1 0;
    }}

    InputModal .input-field {{
        width: 100%;
        background: {DraculaColors.BACKGROUND.value};
        border: solid {DraculaColors.SELECTION.value};
        margin-bottom: 1;
    }}

    InputModal .input-field:focus {{
        border: solid {DraculaColors.PURPLE.value};
    }}

    InputModal .input-footer {{
        text-align: center;
        color: {DraculaColors.COMMENT.value};
    }}
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(
        self,
        title: str = "Input",
        description: str = "",
        placeholder: str = "",
        default_value: str = "",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.modal_title = title
        self.description = description
        self.placeholder = placeholder
        self.default_value = default_value

    def compose(self) -> ComposeResult:
        with Container(classes="input-container"):
            yield Static(self.modal_title, classes="input-title")
            if self.description:
                yield Static(self.description, classes="input-description")
            yield Input(
                value=self.default_value,
                placeholder=self.placeholder,
                classes="input-field",
                id="input-field",
            )
            yield Static(
                f"[{DraculaColors.CYAN.value}]Enter[/] confirm  "
                f"[{DraculaColors.CYAN.value}]Esc[/] cancel",
                classes="input-footer",
            )

    def on_mount(self) -> None:
        self.query_one("#input-field", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)
