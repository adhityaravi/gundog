"""Daemon server for gundog - persistent query service."""

from importlib import resources
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import APIKeyHeader

from gundog._config import EmbeddingConfig, GundogConfig, StorageConfig
from gundog._daemon_config import DaemonConfig
from gundog._git import build_line_anchor
from gundog._query import QueryEngine


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

    app = FastAPI(title="gundog daemon", docs_url=None, redoc_url=None)

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

    # Index manager
    manager = IndexManager(config)

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
            "available_indexes": list(config.indexes.keys()),
        }

    @app.get("/api/indexes")
    async def list_indexes(_: None = Depends(verify_api_key)) -> dict:
        return {
            "indexes": config.indexes,
            "active": manager.active_index,
            "default": config.default_index,
        }

    @app.post("/api/indexes/active")
    async def set_active_index(
        name: str = Query(...),
        _: None = Depends(verify_api_key),
    ) -> dict:
        if name not in config.indexes:
            raise HTTPException(status_code=404, detail=f"Unknown index: {name}")

        manager.load_index(name)
        return {"active": manager.active_index}

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
                    "url": build_file_url(d),
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

    # Warmup on startup - pre-load default index and embedding model
    @app.on_event("startup")
    async def warmup() -> None:
        if config.default_index:
            try:
                print(f"Warming up: loading index '{config.default_index}'...")
                engine = manager.ensure_loaded()
                # Run a dummy query to initialize the embedding model
                engine.query("warmup", top_k=1)
                print("Warmup complete - ready for queries")
            except Exception as e:
                print(f"Warmup failed (non-fatal): {e}")

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
