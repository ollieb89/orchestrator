# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Distributed Grid is a GPU cluster orchestration tool built with Python 3.11+. It manages distributed computing across multiple nodes using Ray for task execution and SSH for node management.

## Common Commands

```bash
# Install dependencies
poetry install
make install-system   # Install 'grid' CLI system-wide to ~/.local/bin

# Run tests
poetry run pytest -v
poetry run pytest tests/test_config.py           # Single test file
poetry run pytest -k "test_cluster"              # Tests matching pattern

# Code quality
poetry run ruff format .                          # Format
poetry run ruff check . --fix                     # Lint with auto-fix
poetry run mypy src                               # Type checking

# CLI usage (after install-system)
grid --help
grid cluster start -c config/my-cluster-enhanced.yaml
grid cluster status -c config/my-cluster-enhanced.yaml
grid boost request gpu-master cpu 2.0 --priority high

# Auto-offload management
grid offload auto --enable                    # Enable automatic offloading from head node
grid offload auto --enable --threshold 70     # Enable with custom memory threshold
grid offload auto --enable --threshold cpu=80 --threshold memory=65 --threshold gpu=90
grid offload auto --disable                   # Disable automatic offloading
grid offload auto --status                    # Show current auto-offload status

# Interactive dashboard
grid offload watch                            # Launch real-time offload dashboard
grid offload watch --interval 2               # Refresh every 2 seconds
```

## Architecture

### Core Components

- **GridOrchestrator** (`src/distributed_grid/core/orchestrator.py`): Central coordinator that ties together SSH management, health checking, command execution, and resource sharing
- **SSHManager** (`src/distributed_grid/core/ssh_manager.py`): Manages paramiko SSH connections to cluster nodes, respects `~/.ssh/config`
- **RayClusterManager** (`src/distributed_grid/cluster/__init__.py`): Handles Ray head/worker node lifecycle (install, start, stop, status)

### Orchestration Layer (`src/distributed_grid/orchestration/`)

- **ResourceSharingOrchestrator**: Coordinates resource sharing across the cluster
- **ResourceBoostManager**: Enables master node to borrow CPU/GPU/memory from workers
- **IntelligentScheduler**: Smart job scheduling based on node resources
- **OffloadingExecutor/OffloadingDetector**: Automatic task offloading when nodes are under pressure
- **DistributedMemoryPool**: Shared memory across cluster nodes

### Configuration (`src/distributed_grid/config/`)

- **ClusterConfig**: Main config model loaded from YAML (nodes, execution, logging, resource_sharing)
- **NodeConfig**: Per-node config (host, user, gpu_count, memory_gb, role, tags)
- Default config path: `config/my-cluster-enhanced.yaml`

### Key Patterns

- Async throughout: Uses `asyncio` for concurrent SSH operations and Ray interactions
- Pydantic models for all configuration and data classes
- structlog for structured logging
- Rich/Typer/Click for CLI with colored output

## Testing

- Tests use `pytest-asyncio` with `asyncio_mode = "auto"`
- Fixtures in `tests/conftest.py` provide `sample_cluster_config`, `mock_orchestrator`, etc.
- Tests mock SSH connections to avoid requiring actual cluster nodes

## Ray Cluster Notes

- Head node is first in config's nodes list, workers are the rest
- Ray environment variables configure timeouts (heartbeat, GCS, gRPC) - see `cluster/__init__.py`
- GCS startup wait is critical; workers connect sequentially with delays to avoid thundering herd
