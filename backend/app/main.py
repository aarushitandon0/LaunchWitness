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
from app.routers import businesses, health, internal, launch, report
from app.sites import routes as seller_routes

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


def start_monitor(settings: Settings):
    """Light monitoring (SPEC §7). Off with MONITOR_ENABLED=false; tests never run this."""
    from app.agents.claude_client import make_claude_client
    from app.db import get_engine
    from app.integrations import for_business, get_integrations, get_practice_integrations
    from app.monitor.scheduler import Monitor

    engine = get_engine()
    claude = make_claude_client(settings, engine if settings.claude_mode == "live" else None)
    monitor = Monitor(engine, settings, lambda b: for_business(b, get_integrations(), get_practice_integrations()),
                      claude)
    monitor.start()
    return monitor


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    settings = get_settings()
    monitor = start_monitor(settings) if settings.monitor_enabled else None
    yield
    if monitor is not None:
        monitor.shutdown()


def create_app(*, frontend_dist: Path = FRONTEND_DIST, run_lifespan: bool = True) -> FastAPI:
    app = FastAPI(title="LaunchWitness", lifespan=lifespan if run_lifespan else None)
    app.include_router(health.router)
    app.include_router(internal.router)
    app.include_router(businesses.router)
    app.include_router(launch.router)
    app.include_router(report.router)
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
