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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
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
    except Exception as exc:  # pragma: no cover - depends on environment
        return {"status": "degraded", "database": "unreachable", "detail": str(exc)[:200]}
