"""FastAPI app: API routers, internal endpoints, seller sites and the built frontend.

Requests whose Host is a seller site (`<subdomain>.APP_DOMAIN` or a seller's
own domain in the DB) get that seller's pages; everything else gets the app.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from sqlmodel import Session

from app.config import REPO_ROOT, Settings, get_settings
from app.db import get_session, init_db
from app.routers import businesses, health, internal, launch
from app.sites import routes as seller_routes

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


def create_app(*, frontend_dist: Path = FRONTEND_DIST, run_lifespan: bool = True) -> FastAPI:
    app = FastAPI(title="LaunchWitness", lifespan=lifespan if run_lifespan else None)
    app.include_router(health.router)
    app.include_router(internal.router)
    app.include_router(businesses.router)
    app.include_router(launch.router)
    app.include_router(seller_routes.router)

    assets = frontend_dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(
        path: str,
        request: Request,
        settings: Annotated[Settings, Depends(get_settings)],
        session: Annotated[Session, Depends(get_session)],
    ):
        if path.startswith(("api/", "internal/")):
            raise HTTPException(status_code=404)
        page = seller_routes.seller_page(path, request, settings, session)
        if page is not None:
            return page
        index = frontend_dist / "index.html"
        if not index.is_file():
            return PlainTextResponse("Frontend not built. Run: cd frontend && npm run build")
        return FileResponse(index)

    return app


app = create_app()
