"""HTTP and WebSocket client for gundog daemon.

This module provides the DaemonClient class for communicating with a gundog
daemon. It supports both HTTP (for simple queries) and WebSocket (for
streaming/TUI use cases).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import httpx
import websockets
from websockets import ClientConnection

from gundog_core.config import DaemonAddress
from gundog_core.errors import ConnectionError, QueryError
from gundog_core.types import (
    GraphData,
    GraphEdge,
    GraphNode,
    IndexInfo,
    QueryResponse,
    RelatedHit,
    SearchHit,
)

if TYPE_CHECKING:
    pass


class DaemonClient:
    """Client for communicating with gundog daemon.

    Supports both HTTP (for simple queries) and WebSocket (for streaming/TUI).

    Usage:
        # Async context manager (recommended)
        async with DaemonClient() as client:
            result = await client.query("authentication")

        # Manual lifecycle
        client = DaemonClient()
        await client.connect()
        try:
            result = await client.query("authentication")
        finally:
            await client.disconnect()
    """

    def __init__(
        self,
        address: DaemonAddress | None = None,
        *,
        timeout: float = 30.0,
        auto_reconnect: bool = True,
        max_reconnect_delay: float = 30.0,
    ) -> None:
        """Initialize the daemon client.

        Args:
            address: Daemon address. Defaults to localhost:7676.
            timeout: Request timeout in seconds.
            auto_reconnect: Whether to auto-reconnect on connection loss.
            max_reconnect_delay: Maximum delay between reconnect attempts.
        """
        self._address = address or DaemonAddress()
        self._timeout = timeout
        self._auto_reconnect = auto_reconnect
        self._max_reconnect_delay = max_reconnect_delay
        self._http: httpx.AsyncClient | None = None
        self._ws: ClientConnection | None = None
        self._connected = False

    async def __aenter__(self) -> DaemonClient:
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.disconnect()

    @property
    def is_connected(self) -> bool:
        """Check if connected to daemon."""
        return self._connected

    @property
    def address(self) -> DaemonAddress:
        """Get the daemon address."""
        return self._address

    # -------------------------------------------------------------------------
    # Connection Management
    # -------------------------------------------------------------------------

    async def connect(self) -> None:
        """Establish HTTP client connection.

        Raises:
            ConnectionError: If daemon is unreachable.
        """
        self._http = httpx.AsyncClient(
            base_url=self._address.http_url,
            timeout=self._timeout,
        )
        try:
            resp = await self._http.get("/api/health")
            resp.raise_for_status()
            self._connected = True
        except httpx.HTTPError as e:
            await self._http.aclose()
            self._http = None
            raise ConnectionError(f"Cannot reach daemon at {self._address.http_url}: {e}") from e

    async def disconnect(self) -> None:
        """Close all connections."""
        if self._ws:
            await self._ws.close()
            self._ws = None
        if self._http:
            await self._http.aclose()
            self._http = None
        self._connected = False

    # -------------------------------------------------------------------------
    # HTTP API
    # -------------------------------------------------------------------------

    async def query(
        self,
        q: str,
        *,
        top_k: int = 10,
        index: str | None = None,
        expand: bool = True,
        expand_depth: int = 1,
        min_score: float = 0.5,
    ) -> QueryResponse:
        """Execute semantic search via HTTP.

        Args:
            q: Search query text.
            top_k: Maximum number of results to return.
            index: Index name to query. Uses daemon's active index if not specified.
            expand: Whether to expand results via similarity graph.
            expand_depth: Maximum graph traversal depth.
            min_score: Minimum similarity score threshold.

        Returns:
            QueryResponse with direct and related matches.

        Raises:
            ConnectionError: If not connected.
            QueryError: If query execution fails.
        """
        if not self._http:
            raise ConnectionError("Not connected")

        params: dict[str, Any] = {
            "q": q,
            "k": top_k,
            "expand": str(expand).lower(),
            "expand_depth": expand_depth,
            "min_score": min_score,
        }
        if index:
            params["index"] = index

        try:
            resp = await self._http.get("/api/query", params=params)
            resp.raise_for_status()
            return self._parse_query_response(resp.json())
        except httpx.HTTPStatusError as e:
            raise QueryError(f"Query failed: {e.response.status_code}") from e
        except httpx.HTTPError as e:
            raise QueryError(f"Query failed: {e}") from e

    async def list_indexes(self) -> list[IndexInfo]:
        """List available indexes.

        Returns:
            List of IndexInfo for all registered indexes.

        Raises:
            ConnectionError: If not connected.
        """
        if not self._http:
            raise ConnectionError("Not connected")

        resp = await self._http.get("/api/indexes")
        resp.raise_for_status()
        data = resp.json()
        return [
            IndexInfo(
                name=idx["name"],
                path=idx["path"],
                file_count=idx.get("file_count", 0),
                is_active=idx.get("is_active", False),
            )
            for idx in data.get("indexes", [])
        ]

    async def switch_index(self, name: str) -> bool:
        """Switch active index.

        Args:
            name: Name of the index to activate.

        Returns:
            True if switch was successful.

        Raises:
            ConnectionError: If not connected.
        """
        if not self._http:
            raise ConnectionError("Not connected")

        resp = await self._http.post("/api/indexes/active", json={"name": name})
        return resp.status_code == 200

    async def get_status(self) -> dict[str, Any]:
        """Get daemon status.

        Returns:
            Dict with daemon status information.

        Raises:
            ConnectionError: If not connected.
        """
        if not self._http:
            raise ConnectionError("Not connected")

        resp = await self._http.get("/api/health")
        resp.raise_for_status()
        return resp.json()

    # -------------------------------------------------------------------------
    # WebSocket API (for TUI streaming)
    # -------------------------------------------------------------------------

    @asynccontextmanager
    async def websocket(self) -> AsyncIterator[ClientConnection]:
        """Context manager for WebSocket connection.

        Usage:
            async with client.websocket() as ws:
                await ws.send(json.dumps({"type": "query", "query": "auth"}))
                response = await ws.recv()

        Yields:
            WebSocket connection to the daemon.
        """
        async with websockets.connect(
            self._address.ws_url,
            ping_interval=30,
            ping_timeout=10,
        ) as ws:
            yield ws

    async def query_streaming(
        self,
        q: str,
        *,
        top_k: int = 10,
        index: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Execute query via WebSocket with streaming results.

        Yields partial results as they become available.

        Args:
            q: Search query text.
            top_k: Maximum number of results.
            index: Index name to query.

        Yields:
            Dict messages from the daemon (partial results, final result).
        """
        async with self.websocket() as ws:
            request: dict[str, Any] = {
                "type": "query",
                "query": q,
                "top_k": top_k,
            }
            if index:
                request["index"] = index

            await ws.send(json.dumps(request))

            while True:
                try:
                    message = await ws.recv()
                    data = json.loads(message)
                    yield data
                    if data.get("type") == "query_result":
                        break
                except websockets.ConnectionClosed:
                    break

    # -------------------------------------------------------------------------
    # Response Parsing
    # -------------------------------------------------------------------------

    def _parse_lines(self, lines: str | list | tuple | None) -> tuple[int, int] | None:
        """Parse lines field which may be string '1-48' or tuple/list.

        Args:
            lines: Line range in various formats (string, list, tuple, or None)

        Returns:
            Tuple of (start_line, end_line) or None
        """
        if lines is None:
            return None
        if isinstance(lines, str):
            parts = lines.split("-")
            if len(parts) == 2:
                try:
                    return (int(parts[0]), int(parts[1]))
                except ValueError:
                    return None
            return None
        if isinstance(lines, (list, tuple)) and len(lines) >= 2:
            try:
                return (int(lines[0]), int(lines[1]))
            except (ValueError, TypeError):
                return None
        return None

    def _parse_query_response(self, data: dict[str, Any]) -> QueryResponse:
        """Parse raw JSON into QueryResponse."""
        direct = [
            SearchHit(
                path=h["path"],
                score=h["score"],
                type=h.get("type", "code"),
                lines=self._parse_lines(h.get("lines")),
                chunk_index=h.get("chunk_index"),
                content_preview=h.get("preview"),
            )
            for h in data.get("direct", data.get("results", []))
        ]

        related = [
            RelatedHit(
                path=r["path"],
                via=r["via"],
                edge_weight=r.get("edge_weight", r.get("weight", 0.0)),
                depth=r.get("depth", 1),
                type=r.get("type", "code"),
            )
            for r in data.get("related", [])
        ]

        # Build graph from direct and related results (like WebUI does)
        seen_ids: set[str] = set()
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        # Add direct results as nodes
        for hit in direct:
            if hit.path not in seen_ids:
                seen_ids.add(hit.path)
                nodes.append(
                    GraphNode(
                        id=hit.path,
                        type=hit.type,
                        score=hit.score,
                    )
                )

        # Add related results as nodes and create edges
        for rel in related:
            if rel.path not in seen_ids:
                seen_ids.add(rel.path)
                nodes.append(
                    GraphNode(
                        id=rel.path,
                        type=rel.type,
                        score=None,
                    )
                )

            # Create edge from via -> path (only if via exists in nodes)
            if rel.via in seen_ids:
                edges.append(
                    GraphEdge(
                        source=rel.via,
                        target=rel.path,
                        weight=rel.edge_weight,
                    )
                )

        graph = GraphData(nodes=nodes, edges=edges) if nodes else None

        return QueryResponse(
            direct=direct,
            related=related,
            graph=graph,
            timing_ms=data.get("timing_ms", 0.0),
            total_matches=data.get("total", len(direct)),
        )
