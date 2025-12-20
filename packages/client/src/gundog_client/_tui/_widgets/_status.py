"""Status bar widget for connection and index status.

Shows connection state, daemon URL, active index, and query timing.
"""

from __future__ import annotations

from enum import Enum

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class ConnectionState(Enum):
    """Connection states for the daemon."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"


class StatusBar(Widget):
    """Status bar showing connection and index information.

    Display format matches WebUI style with connection indicator,
    daemon URL, active index, and query timing.
    """

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    StatusBar > Horizontal {
        width: 100%;
        height: 100%;
    }

    StatusBar .status-item {
        padding: 0 1;
    }

    StatusBar .connection-status {
        width: auto;
    }

    StatusBar .connected {
        color: $success;
    }

    StatusBar .disconnected {
        color: $error;
    }

    StatusBar .connecting {
        color: $warning;
    }

    StatusBar .daemon-url {
        color: $text-muted;
    }

    StatusBar .index-info {
        color: $text;
    }

    StatusBar .local-path {
        color: $text-muted;
    }

    StatusBar .timing {
        color: $text-muted;
    }

    StatusBar .spacer {
        width: 1fr;
    }
    """

    connection_state: reactive[ConnectionState] = reactive(
        ConnectionState.DISCONNECTED, init=False
    )
    daemon_url: reactive[str] = reactive("", init=False)
    active_index: reactive[str | None] = reactive(None, init=False)
    file_count: reactive[int] = reactive(0, init=False)
    local_path: reactive[str | None] = reactive(None, init=False)
    query_timing_ms: reactive[float | None] = reactive(None, init=False)

    def __init__(
        self,
        *,
        daemon_url: str = "",
        local_path: str | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the status bar.

        Args:
            daemon_url: URL of the daemon to display.
            local_path: Local path for file preview.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        # Store initial values - will be applied in on_mount
        self._init_daemon_url = daemon_url
        self._init_local_path = local_path

    def compose(self) -> ComposeResult:
        """Compose the status bar layout."""
        with Horizontal():
            yield Static("", classes="status-item connection-status", id="connection-indicator")
            yield Static("", classes="status-item daemon-url", id="daemon-url")
            yield Static("", classes="status-item index-info", id="index-info")
            yield Static("", classes="status-item local-path", id="local-path")
            yield Static("", classes="spacer")
            yield Static("", classes="status-item timing", id="timing")

    def on_mount(self) -> None:
        """Update all status items on mount."""
        # Apply initial values now that compose has run
        if self._init_daemon_url:
            self.daemon_url = self._init_daemon_url
        if self._init_local_path:
            self.local_path = self._init_local_path
        # Update all displays
        self._update_connection_indicator()
        self._update_daemon_url()
        self._update_index_info()
        self._update_local_path()
        self._update_timing()

    def watch_connection_state(self, state: ConnectionState) -> None:
        """Update connection indicator when state changes."""
        self._update_connection_indicator()

    def watch_daemon_url(self, url: str) -> None:
        """Update daemon URL display."""
        self._update_daemon_url()

    def watch_active_index(self, index: str | None) -> None:
        """Update index info display."""
        self._update_index_info()

    def watch_file_count(self, count: int) -> None:
        """Update index info display."""
        self._update_index_info()

    def watch_local_path(self, path: str | None) -> None:
        """Update local path display."""
        self._update_local_path()

    def watch_query_timing_ms(self, timing: float | None) -> None:
        """Update timing display."""
        self._update_timing()

    def _update_connection_indicator(self) -> None:
        """Update the connection status indicator."""
        indicator = self.query_one("#connection-indicator", Static)

        if self.connection_state == ConnectionState.CONNECTED:
            indicator.update("[connected]* connected[/connected]")
            indicator.remove_class("disconnected", "connecting")
            indicator.add_class("connected")
        elif self.connection_state == ConnectionState.CONNECTING:
            indicator.update("[connecting]~ connecting[/connecting]")
            indicator.remove_class("connected", "disconnected")
            indicator.add_class("connecting")
        else:
            indicator.update("[disconnected]x disconnected[/disconnected]")
            indicator.remove_class("connected", "connecting")
            indicator.add_class("disconnected")

    def _update_daemon_url(self) -> None:
        """Update the daemon URL display."""
        url_widget = self.query_one("#daemon-url", Static)
        if self.daemon_url:
            url_widget.update(f"[daemon-url]{self.daemon_url}[/daemon-url]")
        else:
            url_widget.update("")

    def _update_index_info(self) -> None:
        """Update the index info display."""
        info_widget = self.query_one("#index-info", Static)
        if self.active_index:
            if self.file_count > 0:
                info_widget.update(
                    f"[index-info]{self.active_index} ({self.file_count:,} files)[/index-info]"
                )
            else:
                info_widget.update(f"[index-info]{self.active_index}[/index-info]")
        else:
            info_widget.update("[index-info]no index[/index-info]")

    def _update_local_path(self) -> None:
        """Update the local path display."""
        path_widget = self.query_one("#local-path", Static)
        if self.local_path:
            # Shorten path for display
            display_path = self.local_path
            if len(display_path) > 30:
                display_path = "..." + display_path[-27:]
            path_widget.update(f"[local-path][path] {display_path}[/local-path]")
        else:
            path_widget.update("[local-path][path?] [L][/local-path]")

    def _update_timing(self) -> None:
        """Update the timing display."""
        timing_widget = self.query_one("#timing", Static)
        if self.query_timing_ms is not None:
            timing_widget.update(f"[timing]{self.query_timing_ms:.1f}ms[/timing]")
        else:
            timing_widget.update("")

    def set_connected(self, url: str, index: str | None = None, file_count: int = 0) -> None:
        """Set the connected state with daemon info."""
        self.connection_state = ConnectionState.CONNECTED
        self.daemon_url = url
        self.active_index = index
        self.file_count = file_count

    def set_connecting(self, url: str) -> None:
        """Set the connecting state."""
        self.connection_state = ConnectionState.CONNECTING
        self.daemon_url = url

    def set_disconnected(self) -> None:
        """Set the disconnected state."""
        self.connection_state = ConnectionState.DISCONNECTED
        self.query_timing_ms = None

    def set_query_timing(self, timing_ms: float) -> None:
        """Set the query timing."""
        self.query_timing_ms = timing_ms

    def set_local_path_configured(self, path: str | None) -> None:
        """Set whether local path is configured for preview/edit."""
        self.local_path = path
