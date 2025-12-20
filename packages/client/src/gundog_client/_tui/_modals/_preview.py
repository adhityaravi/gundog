"""Preview modal for file content display with syntax highlighting."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import ClassVar

from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Markdown, Static

from gundog_client._tui._constants import PreviewConfig
from gundog_client._tui._theme import DraculaColors, get_language_for_file

logger = logging.getLogger(__name__)


class PreviewModal(ModalScreen[None]):
    """Modal popup showing file preview with syntax highlighting."""

    DEFAULT_CSS = f"""
    PreviewModal {{
        align: center middle;
    }}

    PreviewModal .preview-container {{
        width: 90%;
        height: 90%;
        background: {DraculaColors.BACKGROUND.value};
        border: solid {DraculaColors.SELECTION.value};
    }}

    PreviewModal .preview-header {{
        height: 1;
        background: {DraculaColors.BACKGROUND.value};
        color: {DraculaColors.COMMENT.value};
        padding: 0 1;
        border-bottom: solid {DraculaColors.SELECTION.value};
    }}

    PreviewModal .preview-scroll {{
        height: 1fr;
        background: {DraculaColors.BACKGROUND.value};
        scrollbar-size: 1 1;
        scrollbar-color: {DraculaColors.SELECTION.value};
    }}

    PreviewModal .preview-code {{
        padding: 0 1;
        background: {DraculaColors.BACKGROUND.value};
    }}

    PreviewModal .preview-footer {{
        height: 1;
        background: {DraculaColors.BACKGROUND.value};
        color: {DraculaColors.COMMENT.value};
        padding: 0 1;
        border-top: solid {DraculaColors.SELECTION.value};
    }}

    PreviewModal .preview-error {{
        padding: 2;
        color: {DraculaColors.RED.value};
        text-align: center;
        background: {DraculaColors.BACKGROUND.value};
    }}
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close", show=False),
        Binding("x", "close", "Close", show=False),
        Binding("q", "close", "Close", show=False),
        Binding("j", "scroll_down", "Down", show=False),
        Binding("k", "scroll_up", "Up", show=False),
        Binding("down", "scroll_down", "Down", show=False),
        Binding("up", "scroll_up", "Up", show=False),
        Binding("g", "scroll_top", "Top", show=False),
        Binding("G", "scroll_bottom", "Bottom", show=False),
        Binding("page_down", "page_down", "Page Down", show=False),
        Binding("page_up", "page_up", "Page Up", show=False),
        Binding("e", "open_editor", "Edit", show=False),
    ]

    def __init__(
        self,
        file_path: str,
        local_base_path: str | None = None,
        start_line: int | None = None,
        end_line: int | None = None,
        context_lines: int = PreviewConfig.DEFAULT_CONTEXT_LINES,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.file_path = file_path
        self.local_base_path = local_base_path
        self.start_line = start_line
        self.end_line = end_line
        self.context_lines = context_lines

        self._content: str | None = None
        self._total_lines: int = 0
        self._display_start: int = 1
        self._language: str = "text"
        self._error: str | None = None
        self._full_path: Path | None = None

    def on_mount(self) -> None:
        self._load_content()

    def _load_content(self) -> None:
        if not self.local_base_path:
            self._error = "Local path not configured. Press L to set."
            return

        self._full_path = Path(self.local_base_path) / self.file_path

        if not self._full_path.exists():
            self._error = f"File not found: {self._full_path}"
            return

        try:
            content = self._full_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            self._total_lines = len(lines)
            self._language = get_language_for_file(self.file_path)

            if self.start_line is not None:
                actual_start = max(1, self.start_line - self.context_lines)
                actual_end = min(
                    self._total_lines,
                    (self.end_line or self.start_line) + self.context_lines,
                )
                lines = lines[actual_start - 1 : actual_end]
                self._display_start = actual_start
            else:
                self._display_start = 1

            self._content = "\n".join(lines)
        except Exception as e:
            logger.error("Error reading file: %s", e)
            self._error = f"Error reading file: {e}"

    def compose(self) -> ComposeResult:
        with Container(classes="preview-container"):
            yield Static(
                f"[{DraculaColors.COMMENT.value}]{self.file_path}[/]",
                classes="preview-header",
            )

            if self._error:
                yield Static(self._error, classes="preview-error")
            else:
                with VerticalScroll(classes="preview-scroll", id="preview-scroll"):
                    code = self._render_code()
                    if isinstance(code, Markdown):
                        yield code
                    else:
                        yield Static(code, classes="preview-code", id="preview-code")

            yield Static(self._render_footer(), classes="preview-footer")

    def _render_code(self) -> Syntax | Markdown | str:
        if not self._content:
            return "Loading..."

        if self._language == "markdown":
            md_lines = self._content.splitlines()[: PreviewConfig.MARKDOWN_LINE_LIMIT]
            return Markdown("\n".join(md_lines))

        return Syntax(
            self._content,
            self._language,
            theme="dracula",
            line_numbers=True,
            start_line=self._display_start,
            background_color=DraculaColors.BACKGROUND.value,
        )

    def _render_footer(self) -> str:
        if self._error:
            return f"[{DraculaColors.CYAN.value}]Esc[/] close"

        if not self._content:
            return "Loading..."

        lines = len(self._content.splitlines())
        return (
            f"[{DraculaColors.PURPLE.value}]{self._language}[/]  "
            f"L{self._display_start}-{self._display_start + lines - 1}/{self._total_lines}  "
            f"[{DraculaColors.CYAN.value}]j/k[/] scroll  "
            f"[{DraculaColors.CYAN.value}]e[/] edit  "
            f"[{DraculaColors.CYAN.value}]Esc[/] close"
        )

    def action_close(self) -> None:
        self.dismiss(None)

    def action_scroll_down(self) -> None:
        self.query_one("#preview-scroll", VerticalScroll).scroll_down()

    def action_scroll_up(self) -> None:
        self.query_one("#preview-scroll", VerticalScroll).scroll_up()

    def action_scroll_top(self) -> None:
        self.query_one("#preview-scroll", VerticalScroll).scroll_home()

    def action_scroll_bottom(self) -> None:
        self.query_one("#preview-scroll", VerticalScroll).scroll_end()

    def action_page_down(self) -> None:
        self.query_one("#preview-scroll", VerticalScroll).scroll_page_down()

    def action_page_up(self) -> None:
        self.query_one("#preview-scroll", VerticalScroll).scroll_page_up()

    def action_open_editor(self) -> None:
        if not self._full_path or not self._full_path.exists():
            self.notify("Cannot open: file not found", severity="error")
            return

        editor = os.environ.get("EDITOR", "vi")
        args = [editor]

        if self.start_line:
            args.append(f"+{self.start_line}")

        args.append(str(self._full_path))

        with self.app.suspend():
            try:
                subprocess.run(args)
            except Exception as e:
                logger.error("Failed to open editor: %s", e)
