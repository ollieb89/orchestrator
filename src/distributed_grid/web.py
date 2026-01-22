"""FastAPI web application for Distributed Grid."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from distributed_grid.api.v1.router import api_router
from distributed_grid.config import Settings
from distributed_grid.monitoring import MetricsCollector
from distributed_grid.utils.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifespan."""
    # Startup
    settings = Settings()
    setup_logging(settings.logging.level)
    
    # Initialize monitoring
    metrics = MetricsCollector()
    app.state.metrics = metrics
    
    # TODO: Initialize other components
    
    yield
    
    # Shutdown
    await metrics.stop_collection()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = Settings()
    
    app = FastAPI(
        title="Distributed Grid API",
        description="Optimized distributed GPU cluster orchestration",
        version="0.2.0",
        lifespan=lifespan,
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include API routes
    app.include_router(api_router, prefix="/api/v1")
    
    # Root endpoint
    @app.get("/")
    async def root() -> dict[str, str]:
        """Root endpoint."""
        return {
            "message": "Distributed Grid API",
            "version": "0.2.0",
            "docs": "/docs",
        }
    
    return app


def main() -> None:
    """Run the web application."""
    settings = Settings()
    
    uvicorn.run(
        "distributed_grid.web:create_app",
        factory=True,
        host=settings.api.host,
        port=settings.api.port,
        reload=settings.debug,
        log_level=settings.logging.level.lower(),
    )


if __name__ == "__main__":
    main()
