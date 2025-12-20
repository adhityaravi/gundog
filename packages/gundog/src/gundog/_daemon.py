"""Daemon server for gundog - persistent query service."""

import json
import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from importlib import resources
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Security,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import APIKeyHeader

from gundog._config import EmbeddingConfig, GundogConfig, StorageConfig
from gundog._git import build_line_anchor
from gundog._query import QueryEngine

# Import from core
from gundog_core import DaemonConfig

logger = logging.getLogger("gundog.daemon")


class IndexManager:
    """Manages loading and swapping of indexes."""

    def __init__(self, config: DaemonConfig):
        self.config = config
        self._engine: QueryEngine | None = None
        self._active_index: str | None = None

    @property
    def active_index(self) -> str | None:
        return self._active_index

    @property
    def engine(self) -> QueryEngine | None:
        return self._engine

    def get_file_count(self, index_path: str) -> int:
        """Get file count from an index directory."""
        path = Path(index_path)
        gundog_dir = path if path.name == ".gundog" else path / ".gundog"
        index_dir = gundog_dir / "index"

        # Try HNSW store first (hnsw_config.json)
        hnsw_config = index_dir / "hnsw_config.json"
        if hnsw_config.exists():
            try:
                with open(hnsw_config) as f:
                    data = json.load(f)
                    id_to_idx = data.get("id_to_idx", {})
                    # Count unique files (strip #chunk_X suffix)
                    unique_files = {k.split("#")[0] for k in id_to_idx}
                    return len(unique_files)
            except Exception:
                pass

        # Try numpy store (index.json)
        index_json = index_dir / "index.json"
        if index_json.exists():
            try:
                with open(index_json) as f:
                    data = json.load(f)
                    id_to_idx = data.get("id_to_idx", {})
                    unique_files = {k.split("#")[0] for k in id_to_idx}
                    return len(unique_files)
            except Exception:
                pass

        return 0

    def reload_config(self, warmup: bool = True) -> DaemonConfig:
        """Reload config from disk and optionally warmup default index."""
        self.config = DaemonConfig.load()
        # Reset active index if it no longer exists
        if self._active_index and self._active_index not in self.config.indexes:
            self._active_index = None
            self._engine = None

        if warmup:
            self.warmup()

        return self.config

    def warmup(self) -> bool:
        """Pre-load default index and run a dummy query to initialize embedding model.

        Returns True if warmup succeeded, False otherwise.
        """
        if not self.config.default_index:
            logger.info("No default index configured, skipping warmup")
            return False

        try:
            logger.info(f"Warming up: loading index '{self.config.default_index}'...")
            engine = self.ensure_loaded()
            # Run a dummy query to initialize the embedding model
            engine.query("warmup", top_k=1)
            logger.info("Warmup complete - ready for queries")
            return True
        except Exception as e:
            logger.warning(f"Warmup failed (non-fatal): {e}")
            return False

    def load_index(self, name: str) -> None:
        """Load an index by name, replacing current if different."""
        if name == self._active_index and self._engine is not None:
            return

        index_path = self.config.get_index_path(name)
        if index_path is None:
            raise ValueError(f"Unknown index: {name}")

        # Find the .gundog directory and config
        path = Path(index_path)
        gundog_dir = path if path.name == ".gundog" else path / ".gundog"
        config_file = gundog_dir / "config.yaml"

        if config_file.exists():
            # Load the project's config to get correct backend/model settings
            gundog_config = GundogConfig.load(config_file)
            # Override storage path to be absolute
            gundog_config.storage.path = str(gundog_dir / "index")
        else:
            # Fallback to minimal config
            gundog_config = GundogConfig(
                sources=[],
                embedding=EmbeddingConfig(),
                storage=StorageConfig(path=str(gundog_dir / "index")),
            )

        self._engine = QueryEngine(gundog_config)
        self._active_index = name

    def ensure_loaded(self, index_name: str | None = None) -> QueryEngine:
        """Ensure an index is loaded, using default if not specified."""
        target = index_name or self.config.default_index

        if target is None:
            raise ValueError(
                "No index specified and no default_index configured. "
                "Add an index with: gundog daemon add <name> <path>"
            )

        self.load_index(target)
        assert self._engine is not None
        return self._engine


def create_app(config: DaemonConfig | None = None) -> FastAPI:
    """Create FastAPI application for daemon."""
    if config is None:
        config = DaemonConfig.load()

    # Index manager (created early for lifespan access)
    manager = IndexManager(config)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        """Handle startup/shutdown events."""
        manager.warmup()
        yield

    app = FastAPI(title="gundog daemon", docs_url=None, redoc_url=None, lifespan=lifespan)

    # CORS
    origins = config.daemon.cors.allowed_origins or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # Auth
    api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

    async def verify_api_key(api_key: str | None = Security(api_key_header)) -> None:
        if not config.daemon.auth.enabled:
            return
        if api_key != config.daemon.auth.api_key:
            raise HTTPException(status_code=401, detail="Invalid API key")

    def build_file_url(result: dict) -> str:
        """Build URL from per-file git metadata."""
        git_url = result.get("git_url")
        git_branch = result.get("git_branch")
        git_relative_path = result.get("git_relative_path")

        if not git_url or not git_branch or not git_relative_path:
            return ""

        url = f"{git_url}/blob/{git_branch}/{git_relative_path}"

        lines = result.get("lines")
        if lines:
            start, end = lines.split("-")
            url += build_line_anchor(git_url, int(start), int(end))

        return url

    @app.get("/api/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "active_index": manager.active_index,
            "available_indexes": list(manager.config.indexes.keys()),
        }

    @app.get("/api/indexes")
    async def list_indexes(_: None = Depends(verify_api_key)) -> dict:
        # Return list format compatible with gundog-client
        indexes_list = [
            {
                "name": name,
                "path": path,
                "file_count": manager.get_file_count(path),
                "is_active": name == manager.active_index,
            }
            for name, path in manager.config.indexes.items()
        ]
        return {
            "indexes": indexes_list,
            "active": manager.active_index,
            "default": manager.config.default_index,
        }

    @app.post("/api/indexes/active")
    async def set_active_index(
        name: str = Query(...),
        _: None = Depends(verify_api_key),
    ) -> dict:
        if name not in manager.config.indexes:
            raise HTTPException(status_code=404, detail=f"Unknown index: {name}")

        manager.load_index(name)
        return {"active": manager.active_index}

    @app.post("/api/reload")
    async def reload_config_api(_: None = Depends(verify_api_key)) -> dict:
        """Reload daemon config from disk and warmup default index."""
        new_config = manager.reload_config(warmup=True)
        return {
            "status": "reloaded",
            "indexes": list(new_config.indexes.keys()),
            "default": new_config.default_index,
            "active": manager.active_index,
        }

    @app.get("/api/query")
    async def query_api(
        q: str = Query(..., min_length=1),
        k: int = Query(10, ge=1, le=50),
        index: str | None = Query(None),
        _: None = Depends(verify_api_key),
    ) -> dict:
        try:
            engine = manager.ensure_loaded(index)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None

        result = engine.query(q, top_k=k)

        # Filter out 0% scores and limit related results (consistent with WebUI)
        direct_filtered = [d for d in result.direct if d["score"] > 0]
        related_limited = result.related[:25]  # WebUI uses 25 for graph

        return {
            "query": result.query,
            "index": manager.active_index,
            "direct": [
                {
                    "path": d["path"],
                    "name": Path(d["path"]).name,
                    "type": d["type"],
                    "score": d["score"],
                    "lines": d.get("lines"),
                    "url": d.get("url", ""),  # URL already built by query engine
                }
                for d in direct_filtered
            ],
            "related": [
                {
                    "path": r["path"],
                    "name": Path(r["path"]).name,
                    "type": r["type"],
                    "via": r["via"],
                    "via_name": Path(r["via"]).name,
                    "weight": r["edge_weight"],
                    "url": build_file_url(r),
                }
                for r in related_limited
            ],
        }

    # -------------------------------------------------------------------------
    # WebSocket API (for TUI streaming)
    # -------------------------------------------------------------------------

    def _build_query_result(
        request_id: str | None,
        result: Any,
        timing_ms: float,
    ) -> dict[str, Any]:
        """Build query_result response."""
        # Filter out 0% scores and limit related results (consistent with HTTP API)
        direct_filtered = [d for d in result.direct if d["score"] > 0]
        related_limited = result.related[:25]  # WebUI uses 25 for graph

        return {
            "type": "query_result",
            "id": request_id,
            "timing_ms": timing_ms,
            "direct": [
                {
                    "path": d["path"],
                    "score": d["score"],
                    "type": d.get("type", "code"),
                    "lines": d.get("lines"),
                    "chunk_index": d.get("chunk_index"),
                }
                for d in direct_filtered
            ],
            "related": [
                {
                    "path": r["path"],
                    "via": r["via"],
                    "edge_weight": r["edge_weight"],
                    "depth": r.get("depth", 1),
                    "type": r.get("type", "code"),
                }
                for r in related_limited
            ],
            "graph": {
                "nodes": [
                    {"id": n["path"], "type": n.get("type", "code"), "score": n.get("score")}
                    for n in direct_filtered
                ],
                "edges": [],  # TODO: populate from similarity graph when available
            },
        }

    def _build_index_list() -> dict[str, Any]:
        """Build index_list response."""
        return {
            "type": "index_list",
            "indexes": [
                {
                    "name": name,
                    "files": manager.get_file_count(path),
                    "chunks": 0,
                    "last_updated": None,
                    "config": {},
                    "sample_paths": [],
                }
                for name, path in manager.config.indexes.items()
            ],
            "current": manager.active_index,
        }

    def _build_error(
        request_id: str | None,
        code: str,
        message: str,
    ) -> dict[str, Any]:
        """Build error response."""
        return {
            "type": "error",
            "id": request_id,
            "code": code,
            "message": message,
        }

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        """WebSocket endpoint for TUI streaming communication."""
        await websocket.accept()
        logger.info("WebSocket client connected")

        try:
            while True:
                raw_message = await websocket.receive_text()

                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError:
                    await websocket.send_json(
                        _build_error(None, "INVALID_REQUEST", "Invalid JSON")
                    )
                    continue

                msg_type = message.get("type")
                request_id = message.get("id")

                if msg_type == "query":
                    await _handle_ws_query(websocket, message, request_id)
                elif msg_type == "list_indexes":
                    await websocket.send_json(_build_index_list())
                elif msg_type == "switch_index":
                    await _handle_ws_switch_index(websocket, message, request_id)
                else:
                    await websocket.send_json(
                        _build_error(
                            request_id, "INVALID_REQUEST", f"Unknown message type: {msg_type}"
                        )
                    )

        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected")
        except Exception as e:
            logger.exception(f"WebSocket error: {e}")

    async def _handle_ws_query(
        websocket: WebSocket,
        message: dict[str, Any],
        request_id: str | None,
    ) -> None:
        """Handle query request over WebSocket."""
        query_text = message.get("query", "")
        top_k = message.get("top_k", 10)
        index_name = message.get("index")

        if not query_text:
            await websocket.send_json(
                _build_error(request_id, "INVALID_REQUEST", "Query text is required")
            )
            return

        try:
            start_time = time.perf_counter()
            engine = manager.ensure_loaded(index_name)
            result = engine.query(query_text, top_k=top_k)
            timing_ms = (time.perf_counter() - start_time) * 1000

            await websocket.send_json(_build_query_result(request_id, result, timing_ms))
        except ValueError as e:
            await websocket.send_json(_build_error(request_id, "INDEX_NOT_FOUND", str(e)))
        except Exception as e:
            logger.exception(f"Query failed: {e}")
            await websocket.send_json(_build_error(request_id, "QUERY_FAILED", str(e)))

    async def _handle_ws_switch_index(
        websocket: WebSocket,
        message: dict[str, Any],
        request_id: str | None,
    ) -> None:
        """Handle switch_index request over WebSocket."""
        index_name = message.get("index")

        if not index_name:
            await websocket.send_json(
                _build_error(request_id, "INVALID_REQUEST", "Index name is required")
            )
            return

        if index_name not in manager.config.indexes:
            await websocket.send_json(
                _build_error(request_id, "INDEX_NOT_FOUND", f"Index '{index_name}' does not exist")
            )
            return

        try:
            manager.load_index(index_name)
            await websocket.send_json(
                {
                    "type": "index_switched",
                    "index": index_name,
                    "files": 0,  # TODO: get actual count
                    "sample_paths": [],
                }
            )
        except Exception as e:
            logger.exception(f"Failed to switch index: {e}")
            await websocket.send_json(_build_error(request_id, "INDEX_NOT_FOUND", str(e)))

    # Serve UI if enabled
    if config.daemon.serve_ui:

        @app.get("/", response_class=HTMLResponse)
        async def index() -> str:
            html_file = resources.files("gundog._static").joinpath("index.html")
            html = html_file.read_text()
            html = html.replace("{{TITLE}}", "gundog")
            return html

    return app


def run_daemon(config: DaemonConfig | None = None) -> None:
    """Run the daemon server (blocking)."""
    if config is None:
        config = DaemonConfig.load()

    app = create_app(config)
    uvicorn.run(app, host=config.daemon.host, port=config.daemon.port)


# Expose app factory for ASGI servers (gunicorn, etc.)
# Usage: gunicorn "gundog._daemon:create_app()" -k uvicorn.workers.UvicornWorker
# Or with factory: gunicorn --factory gundog._daemon:create_app -k uvicorn.workers.UvicornWorker
