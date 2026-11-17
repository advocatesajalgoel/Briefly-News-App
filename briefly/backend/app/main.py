"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import admin, bookmarks, health, podcast, stories
from app.config import get_settings

logging.basicConfig(
    level=get_settings().log_level.upper(),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("briefly")

DESCRIPTION = """
Briefly's read API.

**What this API is for.** It serves clustered news stories with the sources that
reported them, and the audio briefings generated from those same stories.

**What it will not do.** It does not republish publishers' articles. Each story
carries the publisher's own headline and a link to the original; the summary and
the narration are written by Briefly from extracted facts.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    scheduler = None
    if settings.scheduler_enabled:
        from app.jobs.scheduler import start_scheduler

        scheduler = start_scheduler()
    log.info("Briefly %s starting in %s", __version__, settings.env)
    yield
    if scheduler is not None:
        from app.jobs.scheduler import shutdown_scheduler

        shutdown_scheduler()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Briefly API",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=False,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["*"],
        )

    app.include_router(health.router)
    app.include_router(stories.router)
    app.include_router(podcast.router)
    app.include_router(bookmarks.router)
    app.include_router(admin.router)

    if settings.storage_backend == "local":
        settings.media_dir.mkdir(parents=True, exist_ok=True)
        app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")

    return app


app = create_app()
