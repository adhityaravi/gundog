"""WebSocket step definitions for integration tests."""

from unittest.mock import patch

from fastapi.testclient import TestClient
from pytest_bdd import given, parsers, then, when

from gundog._daemon import create_app
from gundog_core import DaemonConfig, DaemonSettings


@given("the daemon is running")
def daemon_running(test_context):
    """Start daemon for testing."""
    # Create daemon config with test index
    daemon_config = DaemonConfig(
        daemon=DaemonSettings(host="127.0.0.1", port=7676),
        indexes={"test-index": str(test_context["temp_dir"])},
        default_index="test-index",
    )

    # Create app with patched config loader
    with patch("gundog._daemon.DaemonConfig.load", return_value=daemon_config):
        app = create_app(daemon_config)
        test_context["daemon_app"] = app
        test_context["daemon_config"] = daemon_config
        test_context["test_client"] = TestClient(app)


@when(parsers.parse('I send a WebSocket query for "{query_text}"'))
def send_ws_query(test_context, query_text):
    """Send a query message via WebSocket."""
    client = test_context["test_client"]
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({
            "type": "query",
            "id": "test-request-id",
            "query": query_text,
            "top_k": 10,
        })
        test_context["ws_response"] = websocket.receive_json()


@when("I send a WebSocket list_indexes request")
def send_ws_list_indexes(test_context):
    """Send a list_indexes message via WebSocket."""
    client = test_context["test_client"]
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "list_indexes"})
        test_context["ws_response"] = websocket.receive_json()


@when("I send a WebSocket switch_index request for the test index")
def send_ws_switch_index(test_context):
    """Send a switch_index message via WebSocket."""
    client = test_context["test_client"]
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({
            "type": "switch_index",
            "index": "test-index",
        })
        test_context["ws_response"] = websocket.receive_json()


@when(parsers.parse('I send a WebSocket message with unknown type "{msg_type}"'))
def send_ws_unknown_type(test_context, msg_type):
    """Send a message with unknown type via WebSocket."""
    client = test_context["test_client"]
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({
            "type": msg_type,
            "id": "test-request-id",
        })
        test_context["ws_response"] = websocket.receive_json()


@when("I send a WebSocket query with empty text")
def send_ws_empty_query(test_context):
    """Send a query with empty text via WebSocket."""
    client = test_context["test_client"]
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({
            "type": "query",
            "id": "test-request-id",
            "query": "",
        })
        test_context["ws_response"] = websocket.receive_json()


@then("I should receive a query_result message")
def check_query_result_message(test_context):
    """Verify the response is a query_result message."""
    response = test_context["ws_response"]
    assert response["type"] == "query_result", f"Expected query_result, got {response['type']}"


@then("the result should contain direct matches")
def check_has_direct_matches(test_context):
    """Verify the response contains direct matches."""
    response = test_context["ws_response"]
    assert "direct" in response, "Response should contain 'direct' field"
    assert isinstance(response["direct"], list), "'direct' should be a list"


@then("I should receive an index_list message")
def check_index_list_message(test_context):
    """Verify the response is an index_list message."""
    response = test_context["ws_response"]
    assert response["type"] == "index_list", f"Expected index_list, got {response['type']}"


@then("the list should contain the test index")
def check_list_contains_test_index(test_context):
    """Verify the index list contains the test index."""
    response = test_context["ws_response"]
    assert "indexes" in response, "Response should contain 'indexes' field"
    index_names = [idx["name"] for idx in response["indexes"]]
    assert "test-index" in index_names, f"Expected test-index in {index_names}"


@then("I should receive an index_switched message")
def check_index_switched_message(test_context):
    """Verify the response is an index_switched message."""
    response = test_context["ws_response"]
    assert response["type"] == "index_switched", f"Expected index_switched, got {response['type']}"
    assert response["index"] == "test-index"


@then(parsers.parse('I should receive an error message with code "{error_code}"'))
def check_error_message(test_context, error_code):
    """Verify the response is an error with the expected code."""
    response = test_context["ws_response"]
    assert response["type"] == "error", f"Expected error, got {response['type']}"
    assert response["code"] == error_code, f"Expected code {error_code}, got {response['code']}"
