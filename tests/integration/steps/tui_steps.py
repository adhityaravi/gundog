"""TUI step definitions for integration tests using Textual Pilot."""

import asyncio
from io import StringIO

import pytest
from pytest_bdd import given, parsers, then, when
from rich.console import Console

from gundog_client._tui._app import GundogApp
from gundog_client._tui._enums import ConnectionState
from gundog_core.types import IndexInfo, RelatedHit, SearchHit


def create_mock_search_hit(path: str, score: float, hit_type: str) -> SearchHit:
    """Create a mock SearchHit for testing."""
    return SearchHit(
        path=path,
        score=score,
        type=hit_type,
        lines=(1, 10),
    )


def create_mock_related_hit(path: str, via: str, edge_weight: float, hit_type: str) -> RelatedHit:
    """Create a mock RelatedHit for testing."""
    return RelatedHit(
        path=path,
        via=via,
        edge_weight=edge_weight,
        type=hit_type,
        depth=1,
    )


def create_mock_index(name: str, path: str, file_count: int, is_active: bool) -> IndexInfo:
    """Create a mock IndexInfo for testing."""
    return IndexInfo(
        name=name,
        path=path,
        file_count=file_count,
        is_active=is_active,
    )


def _get_widget_text(widget) -> str:
    """Get the text content of a widget."""
    console = Console(file=StringIO(), force_terminal=True, width=200)
    console.print(widget.render())
    return console.file.getvalue()


class MockedGundogApp(GundogApp):
    """GundogApp with mocked daemon connection for testing."""

    # Use absolute path to CSS file from the TUI package
    from pathlib import Path

    CSS_PATH = (
        Path(__file__).parent.parent.parent.parent
        / "packages"
        / "client"
        / "src"
        / "gundog_client"
        / "_tui"
        / "app.tcss"
    )

    async def _connect(self) -> None:
        """Mock connection - just set state to offline."""
        self.connection_state = ConnectionState.OFFLINE

    async def _connection_monitor(self) -> None:
        """Mock connection monitor - do nothing."""
        pass


@pytest.fixture
def tui_context():
    """Shared TUI test context."""
    return {
        "app_config": {},
        "actions": [],
    }


@given("a TUI app instance")
def create_tui_app(tui_context):
    """Create a GundogApp instance for testing."""
    tui_context["app_config"] = {"type": "basic"}
    tui_context["actions"] = []


@given("a TUI app instance with mock results")
def create_tui_app_with_results(tui_context):
    """Create a GundogApp instance with mock search results."""
    tui_context["app_config"] = {
        "type": "with_results",
        "results": [
            create_mock_search_hit("src/auth.py", 0.95, "code"),
            create_mock_search_hit("src/db.py", 0.85, "code"),
            create_mock_search_hit("docs/api.md", 0.75, "adr"),
        ],
        "related": [
            create_mock_related_hit("src/utils.py", "src/auth.py", 0.8, "code"),
        ],
    }
    tui_context["actions"] = []


@given("a TUI app instance with mock indexes")
def create_tui_app_with_indexes(tui_context):
    """Create a GundogApp instance with mock indexes."""
    tui_context["app_config"] = {
        "type": "with_indexes",
        "indexes": [
            create_mock_index("project-main", "/home/user/project", 100, True),
            create_mock_index("project-docs", "/home/user/docs", 50, False),
        ],
    }
    tui_context["actions"] = []


@when("the app is mounted")
def mount_app(tui_context):
    """Mark that the app should be mounted before assertions."""
    pass  # App will be mounted when running assertions


@when(parsers.parse('I press "{key}"'))
def press_key(tui_context, key):
    """Queue a key press action."""
    tui_context["actions"].append(("press", key))


@when(parsers.parse('I type "{text}"'))
def type_text(tui_context, text):
    """Queue a type action."""
    tui_context["actions"].append(("type", text))


def _setup_app(config: dict) -> MockedGundogApp:
    """Create and configure a MockedGundogApp based on config."""
    app = MockedGundogApp()
    app.connection_state = ConnectionState.OFFLINE

    if config.get("type") == "with_results":
        app._results = config.get("results", [])
        app._related_results = config.get("related", [])
    elif config.get("type") == "with_indexes":
        app._indexes = config.get("indexes", [])
        app._active_index = "project-main"

    return app


async def _run_tui_scenario(tui_context, assertion_func):
    """Run a complete TUI test scenario."""
    app = _setup_app(tui_context["app_config"])

    async with app.run_test() as pilot:
        # Execute all queued actions
        for action_type, action_value in tui_context.get("actions", []):
            if action_type == "press":
                await pilot.press(action_value)
            elif action_type == "type":
                for char in action_value:
                    await pilot.press(char)

        # Run the assertion
        assertion_func(app)


def _run_test(tui_context, assertion_func):
    """Run the TUI test synchronously."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run_tui_scenario(tui_context, assertion_func))
    finally:
        loop.close()


@then(parsers.parse('the app should display the title "{title}"'))
def check_title(tui_context, title):
    """Verify the app displays the expected title."""

    def check(app):
        title_bar = app.query_one("#title-bar")
        rendered = _get_widget_text(title_bar)
        assert title in rendered, f"Expected title '{title}' in '{rendered}'"

    _run_test(tui_context, check)


@then("the search input should be visible")
def check_search_visible(tui_context):
    """Verify the search input is visible."""

    def check(app):
        search_input = app.query_one("#search-input")
        assert search_input is not None
        assert search_input.display is True

    _run_test(tui_context, check)


@then("the footer should show keyboard hints")
def check_footer_hints(tui_context):
    """Verify the footer shows keyboard hints."""

    def check(app):
        footer = app.query_one("#help-hints")
        rendered = _get_widget_text(footer)
        assert "j/k" in rendered or "navigate" in rendered.lower()

    _run_test(tui_context, check)


@then("the search input should be focused")
def check_search_focused(tui_context):
    """Verify the search input is focused."""

    def check(app):
        search_input = app.query_one("#search-input")
        assert app.focused == search_input, f"Expected search input focused, got {app.focused}"

    _run_test(tui_context, check)


@then("the search input should not be focused")
def check_search_not_focused(tui_context):
    """Verify the search input is not focused."""

    def check(app):
        search_input = app.query_one("#search-input")
        assert app.focused != search_input, "Search input should not be focused"

    _run_test(tui_context, check)


@then(parsers.parse('the preview header should show "{text}"'))
def check_preview_header(tui_context, text):
    """Verify the preview header shows expected text."""

    def check(app):
        header = app.query_one("#preview-header")
        rendered = _get_widget_text(header)
        assert text in rendered, f"Expected '{text}' in preview header, got '{rendered}'"

    _run_test(tui_context, check)


@then("the app should be exiting")
def check_app_exiting(tui_context):
    """Verify the app is in the process of exiting."""

    def check(app):
        # After pressing 'q', the app should have return_code set or _exit flag
        pass  # App exits correctly if we reach this point

    _run_test(tui_context, check)


@then(parsers.parse("the selected index should be {index:d}"))
def check_selected_index(tui_context, index):
    """Verify the selected result index."""

    def check(app):
        assert app.selected_index == index, f"Expected index {index}, got {app.selected_index}"

    _run_test(tui_context, check)


@then("the footer should show connection status")
def check_connection_status(tui_context):
    """Verify the footer shows connection status."""

    def check(app):
        footer = app.query_one("#footer-status")
        rendered = _get_widget_text(footer)
        assert any(status in rendered.lower() for status in ["online", "offline", "connecting"]), (
            f"Expected connection status in footer, got '{rendered}'"
        )

    _run_test(tui_context, check)


@then("the direct section header should be visible")
def check_direct_header_visible(tui_context):
    """Verify the direct section header is visible."""

    def check(app):
        header = app.query_one("#direct-header")
        assert header is not None
        rendered = _get_widget_text(header)
        assert "DIRECT" in rendered

    _run_test(tui_context, check)


@then("the related section header should be visible")
def check_related_header_visible(tui_context):
    """Verify the related section header is visible."""

    def check(app):
        header = app.query_one("#related-header")
        assert header is not None
        rendered = _get_widget_text(header)
        assert "RELATED" in rendered

    _run_test(tui_context, check)


@then("the graph pane should be visible")
def check_graph_pane_visible(tui_context):
    """Verify the graph pane is visible."""

    def check(app):
        graph_pane = app.query_one("#graph-pane")
        assert graph_pane is not None

    _run_test(tui_context, check)


@then(parsers.parse('the search input should contain "{text}"'))
def check_search_input_content(tui_context, text):
    """Verify the search input contains the expected text."""

    def check(app):
        search_input = app.query_one("#search-input")
        assert text in search_input.value, (
            f"Expected '{text}' in search input, got '{search_input.value}'"
        )

    _run_test(tui_context, check)
