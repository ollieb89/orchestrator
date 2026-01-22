"""Health check endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Dict

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def health_check() -> Dict[str, str]:
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "distributed-grid",
    }


@router.get("/detailed")
async def detailed_health_check() -> Dict[str, object]:
    """Detailed health check with system status."""
    # TODO: Add actual health checks
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "distributed-grid",
        "version": "0.2.0",
        "components": {
            "database": "healthy",
            "message_queue": "healthy",
            "cluster_nodes": "healthy",
        },
    }
