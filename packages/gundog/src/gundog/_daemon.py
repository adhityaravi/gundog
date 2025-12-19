"""Daemon server for gundog - persistent query service."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from importlib import resources
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, Security
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
                "file_count": 0,  # TODO: get actual count from index
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
                for d in result.direct
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
                for r in result.related
            ],
        }

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
