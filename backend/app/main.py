"""FastAPI application entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)

# Checked before the app object exists, so a misconfigured deployment fails
# with one legible line rather than at the first database call.
settings.assert_deployable()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description=(
        "Design Operations & Ticketing Management System.\n\n"
        "Project -> Design Release -> Template -> Task -> Execution -> Review -> "
        "Revision -> Approval -> Completion, with capacity, efficiency, quality "
        "and delivery measured from transactional data."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["system"])
def health() -> dict:
    """Liveness probe. Deliberately does not touch the database."""
    return {"status": "ok", "environment": settings.ENVIRONMENT}


@app.get("/health/db", tags=["system"])
def health_db() -> dict:
    """Readiness probe: confirms the database answers."""
    from sqlalchemy import text

    from app.db.session import engine

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "database": "reachable"}
    except Exception:  # pragma: no cover - depends on environment
        # This probe is unauthenticated, so it says whether the database
        # answers and nothing else. A driver error carries the host, port and
        # sometimes the user, which is not something to hand to the internet;
        # it goes to the server log, where the operator can read it.
        logger.exception("Database readiness probe failed")
        return {"status": "degraded", "database": "unreachable"}
