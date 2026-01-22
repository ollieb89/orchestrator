"""Distributed Grid - Optimized GPU cluster orchestration."""

__version__ = "0.2.0"
__author__ = "Grid Team"
__email__ = "team@grid.local"

# Core components
from distributed_grid.core import (
    GridOrchestrator,
    GridExecutor,
    SSHManager,
    HealthChecker,
)

# Configuration
from distributed_grid.config import ClusterConfig, Settings

# API layer
from distributed_grid.api import api_router

# Services
from distributed_grid.services import (
    ClusterService,
    NodeService,
    JobService,
)

# Orchestration
from distributed_grid.orchestration import (
    JobScheduler,
    ResourceManager,
    TaskExecutor,
)

# Monitoring
from distributed_grid.monitoring import (
    ClusterHealthChecker,
    MetricsCollector,
    AlertManager,
)

# CLI
from distributed_grid.cli import main

# Web API
from distributed_grid.web import create_app

__all__ = [
    # Version info
    "__version__",
    # Core
    "GridOrchestrator",
    "GridExecutor",
    "SSHManager",
    "HealthChecker",
    # Configuration
    "ClusterConfig",
    "Settings",
    # API
    "api_router",
    # Services
    "ClusterService",
    "NodeService",
    "JobService",
    # Orchestration
    "JobScheduler",
    "ResourceManager",
    "TaskExecutor",
    # Monitoring
    "ClusterHealthChecker",
    "MetricsCollector",
    "AlertManager",
    # CLI
    "main",
    # Web
    "create_app",
]
