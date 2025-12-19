"""Test daemon WebSocket endpoint."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from gundog._daemon import create_app
from gundog_core import DaemonConfig, DaemonSettings


@pytest.fixture
def daemon_config(temp_dir: Path) -> DaemonConfig:
    """Create a daemon config with test indexes."""
    return DaemonConfig(
        daemon=DaemonSettings(host="127.0.0.1", port=7676),
        indexes={"test-index": str(temp_dir)},
        default_index="test-index",
    )


@pytest.fixture
def mock_query_result():
    """Create a mock query result."""
    result = MagicMock()
    result.query = "test query"
    result.direct = [
        {
            "path": "src/main.py",
            "score": 0.95,
            "type": "code",
            "lines": "10-20",
            "chunk_index": 0,
        }
    ]
    result.related = [
        {
            "path": "src/utils.py",
            "via": "src/main.py",
            "edge_weight": 0.8,
            "depth": 1,
            "type": "code",
        }
    ]
    return result


class TestWebSocketEndpoint:
    """Tests for WebSocket endpoint."""

    def test_websocket_connect(self, daemon_config: DaemonConfig):
        """Test WebSocket connection is accepted."""
        with patch("gundog._daemon.DaemonConfig.load", return_value=daemon_config):
            app = create_app(daemon_config)
            client = TestClient(app)

            with client.websocket_connect("/ws") as websocket:
                # Connection should be accepted
                assert websocket is not None

    def test_websocket_invalid_json(self, daemon_config: DaemonConfig):
        """Test WebSocket handles invalid JSON."""
        with patch("gundog._daemon.DaemonConfig.load", return_value=daemon_config):
            app = create_app(daemon_config)
            client = TestClient(app)

            with client.websocket_connect("/ws") as websocket:
                websocket.send_text("not valid json")
                response = websocket.receive_json()

                assert response["type"] == "error"
                assert response["code"] == "INVALID_REQUEST"
                assert "Invalid JSON" in response["message"]

    def test_websocket_unknown_message_type(self, daemon_config: DaemonConfig):
        """Test WebSocket handles unknown message types."""
        with patch("gundog._daemon.DaemonConfig.load", return_value=daemon_config):
            app = create_app(daemon_config)
            client = TestClient(app)

            with client.websocket_connect("/ws") as websocket:
                websocket.send_json({"type": "unknown_type", "id": "123"})
                response = websocket.receive_json()

                assert response["type"] == "error"
                assert response["code"] == "INVALID_REQUEST"
                assert "Unknown message type" in response["message"]

    def test_websocket_list_indexes(self, daemon_config: DaemonConfig):
        """Test list_indexes message."""
        with patch("gundog._daemon.DaemonConfig.load", return_value=daemon_config):
            app = create_app(daemon_config)
            client = TestClient(app)

            with client.websocket_connect("/ws") as websocket:
                websocket.send_json({"type": "list_indexes"})
                response = websocket.receive_json()

                assert response["type"] == "index_list"
                assert "indexes" in response
                assert len(response["indexes"]) == 1
                assert response["indexes"][0]["name"] == "test-index"
                assert response["current"] is None  # No index loaded yet

    def test_websocket_switch_index_success(self, daemon_config: DaemonConfig, temp_dir: Path):
        """Test switch_index message with valid index."""
        # Create minimal index structure
        gundog_dir = temp_dir / ".gundog"
        gundog_dir.mkdir()
        index_dir = gundog_dir / "index"
        index_dir.mkdir()

        with (
            patch("gundog._daemon.DaemonConfig.load", return_value=daemon_config),
            patch("gundog._daemon.QueryEngine"),
        ):
            app = create_app(daemon_config)
            client = TestClient(app)

            with client.websocket_connect("/ws") as websocket:
                websocket.send_json({"type": "switch_index", "index": "test-index"})
                response = websocket.receive_json()

                assert response["type"] == "index_switched"
                assert response["index"] == "test-index"

    def test_websocket_switch_index_not_found(self, daemon_config: DaemonConfig):
        """Test switch_index message with unknown index."""
        with patch("gundog._daemon.DaemonConfig.load", return_value=daemon_config):
            app = create_app(daemon_config)
            client = TestClient(app)

            with client.websocket_connect("/ws") as websocket:
                websocket.send_json({"type": "switch_index", "index": "nonexistent"})
                response = websocket.receive_json()

                assert response["type"] == "error"
                assert response["code"] == "INDEX_NOT_FOUND"

    def test_websocket_switch_index_missing_name(self, daemon_config: DaemonConfig):
        """Test switch_index without index name."""
        with patch("gundog._daemon.DaemonConfig.load", return_value=daemon_config):
            app = create_app(daemon_config)
            client = TestClient(app)

            with client.websocket_connect("/ws") as websocket:
                websocket.send_json({"type": "switch_index"})
                response = websocket.receive_json()

                assert response["type"] == "error"
                assert response["code"] == "INVALID_REQUEST"
                assert "Index name is required" in response["message"]

    def test_websocket_query_missing_query_text(self, daemon_config: DaemonConfig):
        """Test query without query text."""
        with patch("gundog._daemon.DaemonConfig.load", return_value=daemon_config):
            app = create_app(daemon_config)
            client = TestClient(app)

            with client.websocket_connect("/ws") as websocket:
                websocket.send_json({"type": "query", "id": "123"})
                response = websocket.receive_json()

                assert response["type"] == "error"
                assert response["id"] == "123"
                assert response["code"] == "INVALID_REQUEST"
                assert "Query text is required" in response["message"]

    def test_websocket_query_success(
        self, daemon_config: DaemonConfig, mock_query_result, temp_dir: Path
    ):
        """Test query message with valid query."""
        # Create minimal index structure
        gundog_dir = temp_dir / ".gundog"
        gundog_dir.mkdir()
        index_dir = gundog_dir / "index"
        index_dir.mkdir()

        mock_engine = MagicMock()
        mock_engine.query.return_value = mock_query_result

        with (
            patch("gundog._daemon.DaemonConfig.load", return_value=daemon_config),
            patch("gundog._daemon.QueryEngine", return_value=mock_engine),
        ):
            app = create_app(daemon_config)
            client = TestClient(app)

            with client.websocket_connect("/ws") as websocket:
                websocket.send_json({
                    "type": "query",
                    "id": "test-123",
                    "query": "test query",
                    "top_k": 5,
                })
                response = websocket.receive_json()

                assert response["type"] == "query_result"
                assert response["id"] == "test-123"
                assert "timing_ms" in response
                assert "direct" in response
                assert "related" in response
                assert "graph" in response
                assert len(response["direct"]) == 1
                assert response["direct"][0]["path"] == "src/main.py"

    def test_websocket_query_preserves_request_id(
        self, daemon_config: DaemonConfig, mock_query_result, temp_dir: Path
    ):
        """Test that query response includes request ID."""
        gundog_dir = temp_dir / ".gundog"
        gundog_dir.mkdir()
        index_dir = gundog_dir / "index"
        index_dir.mkdir()

        mock_engine = MagicMock()
        mock_engine.query.return_value = mock_query_result

        with (
            patch("gundog._daemon.DaemonConfig.load", return_value=daemon_config),
            patch("gundog._daemon.QueryEngine", return_value=mock_engine),
        ):
            app = create_app(daemon_config)
            client = TestClient(app)

            with client.websocket_connect("/ws") as websocket:
                request_id = "unique-request-id-12345"
                websocket.send_json({
                    "type": "query",
                    "id": request_id,
                    "query": "authentication",
                })
                response = websocket.receive_json()

                assert response["id"] == request_id

    def test_websocket_multiple_messages(self, daemon_config: DaemonConfig):
        """Test handling multiple messages on same connection."""
        with patch("gundog._daemon.DaemonConfig.load", return_value=daemon_config):
            app = create_app(daemon_config)
            client = TestClient(app)

            with client.websocket_connect("/ws") as websocket:
                # First message
                websocket.send_json({"type": "list_indexes"})
                response1 = websocket.receive_json()
                assert response1["type"] == "index_list"

                # Second message
                websocket.send_json({"type": "list_indexes"})
                response2 = websocket.receive_json()
                assert response2["type"] == "index_list"
