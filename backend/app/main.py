"""FastAPI app: API routers, internal endpoints, and the built frontend.

Host-based seller site routing arrives in M2.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.config import REPO_ROOT
from app.db import init_db
from app.routers import health, internal

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


def create_app(*, frontend_dist: Path = FRONTEND_DIST, run_lifespan: bool = True) -> FastAPI:
    app = FastAPI(title="LaunchWitness", lifespan=lifespan if run_lifespan else None)
    app.include_router(health.router)
    app.include_router(internal.router)

    assets = frontend_dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith(("api/", "internal/")):
            raise HTTPException(status_code=404)
        index = frontend_dist / "index.html"
        if not index.is_file():
            return PlainTextResponse("Frontend not built. Run: cd frontend && npm run build")
        return FileResponse(index)

    return app


app = create_app()
