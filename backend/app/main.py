"""FastAPI app: API routers, internal endpoints, seller sites and the built frontend.

Requests whose Host is a seller site (`<subdomain>.APP_DOMAIN` or a seller's
own domain in the DB) get that seller's pages; everything else gets the app.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app.config import REPO_ROOT, Settings, get_settings
from app.db import get_session, init_db
from app.routers import admin, auth, businesses, contact, health, internal, launch, proof, report, watch
from app.safety.request_guard import request_guard
from app.sites import demo as demo_routes
from app.sites import routes as seller_routes
from app.sites.brand import ICON_LINKS

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
REPLAY_PAGE = REPO_ROOT / "replay" / "build.html"  # built by scripts/build-replay.sh, served at /build

# LaunchWitness's own icons (frontend/public, copied into dist by Vite; made by scripts/make_brand_assets.py).
# Served only on the app's own host: a shop host never reaches this list (seller_page answers first).
BRAND_FILES = {
    "favicon.ico": "image/x-icon",
    "favicon-32.png": "image/png",
    "apple-touch-icon.png": "image/png",
    "icon-192.png": "image/png",
    "icon-512.png": "image/png",
    "logo-mark-64.png": "image/png",
    "logo-mark-128.png": "image/png",
    "site.webmanifest": "application/manifest+json",
}

BUILD_COMING_SOON = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>How LaunchWitness was built</title>""" + ICON_LINKS + """
<body style="font-family:system-ui;max-width:560px;margin:15vh auto;padding:0 16px;color:#1f2937;line-height:1.5">
<h1>How this was built: coming soon</h1>
<p>LaunchWitness was built in a series of sessions with Claude Code. The full replay of those sessions will appear
on this page shortly.</p><p><a href="/">← Back to LaunchWitness</a></p></body>"""


def mailer_for(channel: str):
    """The outbox's sender job: practice mail goes to the pretend world, everything else to the real mail server."""
    from app.integrations import get_practice_integrations
    from app.mail.smtp import get_mailer

    return get_practice_integrations().mailer if channel == "practice" else get_mailer()


def start_mail_sender(settings: Settings):
    """MONITOR_ENABLED=false still needs the outbox's sender job (S13): saved emails must go out."""
    from apscheduler.schedulers.background import BackgroundScheduler

    from app import outbox
    from app.db import get_engine
    from app.monitor.scheduler import OUTBOX_SECONDS

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(lambda: outbox.run_once(get_engine(), settings, mailer_for), "interval", seconds=OUTBOX_SECONDS,
                      id="outbox_send", replace_existing=True, max_instances=1, coalesce=True)
    scheduler.start()

    class _Stop:
        def shutdown(self):
            scheduler.shutdown(wait=False)

    return _Stop()


def start_monitor(settings: Settings):
    """Light monitoring (SPEC §7). Off with MONITOR_ENABLED=false; tests never run this."""
    from app.agents.claude_client import make_claude_client
    from app.db import get_engine
    from app.integrations import for_business, get_integrations, get_practice_integrations
    from app.monitor.scheduler import Monitor

    engine = get_engine()
    claude = make_claude_client(settings, engine if settings.claude_mode == "live" else None)
    monitor = Monitor(engine, settings, lambda b: for_business(b, get_integrations(), get_practice_integrations()),
                      claude, team=get_integrations(), mailer_for=mailer_for)
    monitor.start()
    from app.tenancy import purge_old_guest_shops

    monitor.scheduler.add_job(lambda: purge_old_guest_shops(engine, settings, get_practice_integrations()), "interval",
                              hours=1, id="guest_cleanup", replace_existing=True, max_instances=1, coalesce=True)
    logging.getLogger("launchwitness").warning("monitor started (pid %s): jobs=%s", os.getpid(),
                                               sorted(j.id for j in monitor.scheduler.get_jobs()))
    return monitor


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from app import singleton

    # ONE process only: the scheduler runs in-process and SQLite has one writer. A second worker
    # would send every alert and daily test order twice, so it refuses to start.
    singleton.acquire(get_settings().database_url)
    init_db()
    from app.db import get_engine
    from app.startup import reconcile

    closed = reconcile(get_engine())  # close launches / check runs that lost their worker in a restart
    logging.getLogger("launchwitness").warning("startup reconcile: %s", closed)
    settings = get_settings()
    from app.accounts import ensure_admin
    from app.integrations import get_practice_integrations
    from app.tenancy import purge_old_guest_shops

    ensure_admin(get_engine(), settings)  # the ADMIN_EMAIL account exists and is the admin
    from app.selfcheck import warnings

    for w in warnings(settings):  # startup self-check: wrong-for-production settings, never a secret
        logging.getLogger("launchwitness").warning("self-check [%s]: %s", w.code, w.text)
    purge_old_guest_shops(get_engine(), settings, get_practice_integrations())
    monitor = start_monitor(settings) if settings.monitor_enabled else start_mail_sender(settings)
    yield
    if monitor is not None:
        monitor.shutdown()


def create_app(*, frontend_dist: Path = FRONTEND_DIST, replay_page: Path = REPLAY_PAGE,
               run_lifespan: bool = True) -> FastAPI:
    # No /docs, /redoc or /openapi.json: the API is for our own pages, and the route list stays in route_table.py.
    app = FastAPI(title="LaunchWitness", lifespan=lifespan if run_lifespan else None,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.middleware("http")(request_guard)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(internal.router)
    app.include_router(businesses.router)
    app.include_router(launch.router)
    app.include_router(report.router)
    app.include_router(contact.router)
    app.include_router(proof.router)
    app.include_router(watch.router)
    app.include_router(seller_routes.router)
    app.include_router(demo_routes.router)

    assets = frontend_dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    # GET and HEAD: uptime monitors often send HEAD (it used to answer 405). Same handler, no body for HEAD.
    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
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
        if path in BRAND_FILES and (frontend_dist / path).is_file():
            return FileResponse(frontend_dist / path, media_type=BRAND_FILES[path],
                                headers={"Cache-Control": "public, max-age=86400"})
        if path.rstrip("/") == "build":
            if replay_page.is_file():
                return FileResponse(replay_page, media_type="text/html")
            return HTMLResponse(BUILD_COMING_SOON)
        index = frontend_dist / "index.html"
        if not index.is_file():
            return PlainTextResponse("Frontend not built. Run: cd frontend && npm run build")
        return FileResponse(index)

    return app


app = create_app()
