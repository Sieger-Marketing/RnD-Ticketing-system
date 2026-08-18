"""Aggregates every v1 router under a single prefix."""

from fastapi import APIRouter

from app.api.v1 import (
    analytics,
    auth,
    catalog,
    meta,
    notifications,
    projects,
    releases,
    resources,
    reviews,
    settings,
    tasks,
    templates,
    time_entries,
    users,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(catalog.router)
api_router.include_router(meta.router)
api_router.include_router(projects.router)
api_router.include_router(releases.router)
api_router.include_router(templates.router)
api_router.include_router(tasks.router)
api_router.include_router(time_entries.router)
api_router.include_router(reviews.router)
api_router.include_router(resources.router)
api_router.include_router(analytics.router)
api_router.include_router(notifications.router)
api_router.include_router(settings.router)
