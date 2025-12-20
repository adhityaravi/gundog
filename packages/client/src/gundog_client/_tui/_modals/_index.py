"""Index selection modal."""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from gundog_client._tui._theme import DraculaColors
from gundog_core.types import IndexInfo


class IndexItem(Static):
    """Selectable index item."""

    DEFAULT_CSS = f"""
    IndexItem {{
        height: 2;
        padding: 0 1;
        background: {DraculaColors.BACKGROUND.value};
    }}

    IndexItem:hover {{
        background: {DraculaColors.SELECTION.value}30;
    }}

    IndexItem.--selected {{
        background: {DraculaColors.PURPLE.value}20;
        border-left: thick {DraculaColors.PURPLE.value};
    }}
    """

    def __init__(self, index: IndexInfo, **kwargs) -> None:
        super().__init__(**kwargs)
        self.index_info = index

    def compose(self) -> ComposeResult:
        return []

    def on_mount(self) -> None:
        active = f"[{DraculaColors.GREEN.value}]●[/] " if self.index_info.is_active else "  "
        self.update(
            f"{active}[bold {DraculaColors.FOREGROUND.value}]{self.index_info.name}[/]\n"
            f"   [{DraculaColors.COMMENT.value}]{self.index_info.file_count} files  "
            f"{self.index_info.path}[/]"
        )


class IndexModal(ModalScreen[str | None]):
    """Modal for selecting an index."""

    DEFAULT_CSS = f"""
    IndexModal {{
        align: center middle;
    }}

    IndexModal .index-container {{
        width: 60;
        height: auto;
        max-height: 20;
        background: {DraculaColors.BACKGROUND.value};
        border: solid {DraculaColors.SELECTION.value};
        padding: 1;
    }}

    IndexModal .index-title {{
        text-align: center;
        text-style: bold;
        color: {DraculaColors.GREEN.value};
        padding-bottom: 1;
        border-bottom: solid {DraculaColors.SELECTION.value};
    }}

    IndexModal .index-list {{
        height: auto;
        max-height: 14;
        background: {DraculaColors.BACKGROUND.value};
        scrollbar-size: 1 1;
        scrollbar-color: {DraculaColors.SELECTION.value};
    }}

    IndexModal .index-empty {{
        text-align: center;
        color: {DraculaColors.COMMENT.value};
        padding: 2;
    }}

    IndexModal .index-footer {{
        text-align: center;
        color: {DraculaColors.COMMENT.value};
        padding-top: 1;
        border-top: solid {DraculaColors.SELECTION.value};
        margin-top: 1;
    }}
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("q", "cancel", "Cancel", show=False),
        Binding("j", "move_down", "Down", show=False),
        Binding("k", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("up", "move_up", "Up", show=False),
        Binding("enter", "select", "Select", show=True),
    ]

    def __init__(self, indexes: list[IndexInfo], **kwargs) -> None:
        super().__init__(**kwargs)
        self.indexes = indexes
        self._selected_idx = 0

    def compose(self) -> ComposeResult:
        with Container(classes="index-container"):
            yield Static("SELECT INDEX", classes="index-title")

            if self.indexes:
                with VerticalScroll(classes="index-list"):
                    for i, idx in enumerate(self.indexes):
                        item = IndexItem(idx, id=f"index-{i}")
                        if i == 0:
                            item.add_class("--selected")
                        yield item
            else:
                yield Static(
                    "No indexes available\n[dim]gundog daemon add <name> <path>[/]",
                    classes="index-empty",
                )

            yield Static(
                f"[{DraculaColors.CYAN.value}]j/k[/] navigate  "
                f"[{DraculaColors.CYAN.value}]Enter[/] select  "
                f"[{DraculaColors.CYAN.value}]Esc[/] cancel",
                classes="index-footer",
            )

    def _update_selection(self) -> None:
        for i in range(len(self.indexes)):
            item = self.query_one(f"#index-{i}", IndexItem)
            if i == self._selected_idx:
                item.add_class("--selected")
            else:
                item.remove_class("--selected")

    def action_move_down(self) -> None:
        if self.indexes and self._selected_idx < len(self.indexes) - 1:
            self._selected_idx += 1
            self._update_selection()

    def action_move_up(self) -> None:
        if self.indexes and self._selected_idx > 0:
            self._selected_idx -= 1
            self._update_selection()

    def action_select(self) -> None:
        if self.indexes:
            self.dismiss(self.indexes[self._selected_idx].name)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)
