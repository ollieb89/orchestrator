# Project Index: Distributed Grid

Generated: 2026-01-25

## Project Structure

```
distributed-grid/
├── src/distributed_grid/
│   ├── cli.py                 # Main CLI entry point
│   ├── config/                # Configuration models (Pydantic)
│   ├── core/                  # Core orchestration (SSH, executor, health)
│   ├── cluster/               # Ray cluster management
│   ├── orchestration/         # Resource sharing, scheduling, offloading
│   ├── monitoring/            # Metrics, alerting, health checks
│   ├── memory/                # Distributed memory management
│   ├── api/                   # FastAPI REST endpoints
│   ├── services/              # Business logic services
│   └── schemas/               # API request/response schemas
├── tests/                     # 18 test files
├── config/                    # YAML cluster configurations
└── docs/                      # 22 documentation files
```

## Entry Points

| Entry | Path | Description |
|-------|------|-------------|
| CLI | `src/distributed_grid/cli.py` | `grid` command via Click/Typer |
| API | `src/distributed_grid/web.py` | FastAPI server |
| Main | `src/distributed_grid/main.py` | Application bootstrap |

## Core Modules

### cli.py
- **Commands**: `cluster`, `boost`, `memory`, `offload`, `resource_sharing`, `monitor`
- **Subcommands**: install, start, stop, status, request, release, store, retrieve, auto, watch

### core/orchestrator.py
- **Classes**: `GridOrchestrator`, `NodeStatus`, `ClusterStatus`
- **Purpose**: Central coordinator for SSH, health, execution, resource sharing

### core/ssh_manager.py
- **Classes**: `SSHManager`, `SSHCommandResult`
- **Purpose**: Paramiko SSH connections, respects ~/.ssh/config

### cluster/__init__.py
- **Classes**: `RayClusterManager`
- **Purpose**: Ray head/worker lifecycle (install, start, stop, GCS wait)

### orchestration/resource_boost_manager.py
- **Classes**: `ResourceBoostManager`, `ResourceBoost`, `ResourceBoostRequest`
- **Purpose**: Borrow CPU/GPU/memory from workers to master

### orchestration/resource_sharing_orchestrator.py
- **Classes**: `ResourceSharingOrchestrator`
- **Purpose**: Cross-cluster resource sharing, memory spilling, node evacuation

### orchestration/intelligent_scheduler.py
- **Classes**: `IntelligentScheduler`, `SchedulingStrategy`, `TaskPriority`
- **Purpose**: Smart task scheduling (local-first, best-fit, load-balanced, etc.)

### orchestration/distributed_memory_pool.py
- **Classes**: `DistributedMemoryPool`, `DistributedMemoryStore`, `MemoryBlock`
- **Purpose**: Shared memory across cluster via Ray actors

### monitoring/resource_metrics.py
- **Classes**: `ResourceMetricsCollector`, `ResourceSnapshot`, `ResourceType`
- **Purpose**: Real-time CPU/GPU/memory metrics, pressure detection

### config/models.py
- **Classes**: `ClusterConfig`, `NodeConfig`, `ExecutionConfig`, `ResourceSharingConfig`
- **Purpose**: Pydantic models for YAML configuration

## Configuration

| File | Purpose |
|------|---------|
| `pyproject.toml` | Poetry deps, pytest config, CLI script entry |
| `config/my-cluster-enhanced.yaml` | Production cluster config (3 nodes) |
| `.pre-commit-config.yaml` | Pre-commit hooks |

## CLI Commands Quick Reference

```bash
# Cluster management
grid cluster install -c config.yaml
grid cluster start -c config.yaml
grid cluster stop -c config.yaml
grid cluster status -c config.yaml

# Resource boosting
grid boost request <node> <type> <amount>
grid boost release <boost-id>
grid boost status

# Distributed memory
grid memory store <key> <file>
grid memory retrieve <key>
grid memory list-objects

# Resource sharing
grid resource-sharing request <type> <amount>
grid resource-sharing release <alloc-id>
grid resource-sharing status

# Auto-offload management
grid offload auto --enable                    # Enable automatic offloading
grid offload auto --enable --threshold 70     # Enable with custom memory threshold
grid offload auto --enable --threshold cpu=80 --threshold memory=65 --threshold gpu=90
grid offload auto --disable                   # Disable automatic offloading
grid offload auto --status                    # Show current auto-offload status

# Interactive dashboard
grid offload watch                            # Real-time offload monitoring dashboard
grid offload watch --interval 2               # Refresh every 2 seconds
```

## Test Coverage

| Category | Files | Key Tests |
|----------|-------|-----------|
| Unit | 14 | config, utils, core, cli |
| Integration | 3 | boost_aware, memory, resource_sharing |
| Fixtures | `conftest.py` | sample_cluster_config, mock_orchestrator |

## Key Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| ray | ^2.10.0 | Distributed computing |
| paramiko | ^3.0.0 | SSH connections |
| pydantic | ^2.5.0 | Config validation |
| structlog | ^23.1.0 | Structured logging |
| typer/click | ^0.9/^8.0 | CLI framework |
| rich | ^13.7.0 | Terminal formatting |
| fastapi | ^0.110.0 | REST API |

## Quick Start

```bash
# Install
poetry install
make install-system

# Configure cluster
cp config/my-cluster.yaml config/my-cluster-enhanced.yaml
# Edit nodes in YAML

# Start Ray cluster
grid cluster install -c config/my-cluster-enhanced.yaml
grid cluster start -c config/my-cluster-enhanced.yaml

# Run tests
poetry run pytest -v
```

## Architecture Patterns

- **Async-first**: All SSH/Ray ops use asyncio
- **Pydantic models**: All config/data classes
- **Ray actors**: Distributed state (memory stores, metrics)
- **Pressure-based**: Auto-offload when resources stressed
- **Head/Worker topology**: First node is Ray head, rest are workers
