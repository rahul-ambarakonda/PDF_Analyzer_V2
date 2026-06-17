"""FastAPI application factory.

Wires settings, structured logging, CORS, the in-memory job store + background worker, error
handlers, and the API router. The worker/store live on ``app.state`` and are created/destroyed by
the lifespan handler so a graceful shutdown drains the executor.

Run (dev):   uvicorn app.main:app --reload
Run (prod):  uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from comparator.config import Config

from . import __version__
from .api.routes import router
from .config import get_settings
from .errors import register_exception_handlers
from .jobs.store import JobStore
from .jobs.worker import ComparisonWorker
from .logging import RequestContextMiddleware, configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    log = logging.getLogger("app")
    comparator_config = Config.load(settings.comparator_config_path)
    app.state.store = JobStore(
        ttl_seconds=settings.job_ttl_seconds, max_jobs=settings.max_jobs)
    app.state.worker = ComparisonWorker(
        app.state.store, comparator_config, settings.worker_concurrency)
    log.info("startup", extra={"extra_fields": {
        "version": __version__,
        "env": settings.env,
        "worker_concurrency": settings.worker_concurrency,
    }})
    try:
        yield
    finally:
        app.state.worker.shutdown()
        log.info("shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="PDF Text-Fidelity Comparator API",
        version=__version__,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        # Credentials cannot be combined with a "*" origin; enable only for explicit origins.
        allow_credentials=settings.cors_allow_origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    app.include_router(router)
    return app


app = create_app()
