"""
API v1 router configuration
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    batches,
    domains,
    executions,
    grader_test,
    gyms,
    leaderboard,
    monitoring,
    reports,
    tasks,
)

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(domains.router, prefix="/domains", tags=["domains"])
api_router.include_router(gyms.router, prefix="/gyms", tags=["gyms"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(batches.router, prefix="/batches", tags=["batches"])
api_router.include_router(monitoring.router, prefix="/monitoring", tags=["monitoring"])
api_router.include_router(leaderboard.router, prefix="/leaderboard", tags=["leaderboard"])
# Mount reports before executions to ensure static report routes beat dynamic UUID
api_router.include_router(reports.router, prefix="/executions", tags=["reports"])
api_router.include_router(executions.router, prefix="/executions", tags=["executions"])
# Testing endpoint (no auth) for grader config validation
api_router.include_router(grader_test.router, prefix="/grader-test", tags=["testing"])
