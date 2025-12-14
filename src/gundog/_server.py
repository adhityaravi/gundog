"""Web server for interactive gundog queries."""

from importlib import resources
from pathlib import Path
from typing import Any

from gundog._config import GundogConfig
from gundog._query import QueryEngine


def create_app(config: GundogConfig, github_base: str = "", title: str = "gundog") -> Any:
    """Create FastAPI application."""
    try:
        from fastapi import FastAPI, Query
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import HTMLResponse
    except ImportError as e:
        raise ImportError("Install serve extras: pip install gundog[serve]") from e

    app = FastAPI(title=title, docs_url=None, redoc_url=None)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    engine = QueryEngine(config)

    def github_url(path: str, lines: str | None = None) -> str:
        if not github_base:
            return ""
        url = f"{github_base.rstrip('/')}/blob/main/{path}"
        if lines:
            start, end = lines.split("-")
            url += f"#L{start}-L{end}"
        return url

    @app.get("/api/query")
    def query_api(
        q: str = Query(..., min_length=1),
        k: int = Query(10, ge=1, le=50),
    ) -> dict:
        result = engine.query(q, top_k=k)
        return {
            "query": result.query,
            "direct": [
                {
                    "path": d["path"],
                    "name": Path(d["path"]).name,
                    "type": d["type"],
                    "score": d["score"],
                    "lines": d.get("lines"),
                    "url": github_url(d["path"], d.get("lines")),
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
                    "url": github_url(r["path"]),
                }
                for r in result.related
            ],
        }

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        html_file = resources.files("gundog._static").joinpath("index.html")
        html = html_file.read_text()
        # Inject custom title
        html = html.replace("{{TITLE}}", title)
        return html

    return app


def run_server(
    config: GundogConfig,
    host: str = "127.0.0.1",
    port: int = 8000,
    github_base: str = "",
    title: str = "gundog",
) -> None:
    """Start the server."""
    try:
        import uvicorn
    except ImportError as e:
        raise ImportError("Install serve extras: pip install gundog[serve]") from e

    app = create_app(config, github_base, title)
    uvicorn.run(app, host=host, port=port)
