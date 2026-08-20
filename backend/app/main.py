"""FastAPI application entry point."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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


# ---------------------------------------------------------------------------
# Serving the app itself
# ---------------------------------------------------------------------------
#
# When a built frontend is sitting next to this backend, serve it from here.
# The database lives on this machine, so the API lives on this machine, and
# once that is true there is little reason for the app to be somewhere else:
# one process, one origin, no CORS, and nothing else to keep running.
#
# Mounted last, on purpose. Every API route is already registered, so a request
# for /api/... never reaches the catch-all -- and anything the catch-all does
# receive is a client-side route, which means index.html rather than a 404.

_DIST = Path(settings.FRONTEND_DIST_PATH)
if not _DIST.is_absolute():
    _DIST = (Path(__file__).resolve().parents[2] / settings.FRONTEND_DIST_PATH).resolve()

if _DIST.is_dir() and (_DIST / "index.html").is_file():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        """Hand any non-API path to the app and let it route.

        A deep link like /projects/<id> means something to the browser and
        nothing to the server; answering 404 would break every bookmark and
        every refresh.
        """
        candidate = (_DIST / full_path).resolve()
        # Only a real file, and only from inside the build directory: "../" in
        # a URL must not reach the rest of the disk.
        if full_path and candidate.is_file() and _DIST in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")

    logger.info("Serving the built frontend from %s", _DIST)
else:
    logger.info(
        "No built frontend at %s; serving the API only. Run 'npm run build' in "
        "frontend/ to have this process serve the app as well.",
        _DIST,
    )
