"""API v1 endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from distributed_grid.api.v1.endpoints import health, clusters, nodes, jobs

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(clusters.router, prefix="/clusters", tags=["clusters"])
api_router.include_router(nodes.router, prefix="/nodes", tags=["nodes"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
