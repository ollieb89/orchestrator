# Distributed Grid

Optimized distributed GPU cluster orchestration tool built with Python.

## Features

- **Cluster Management**: Manage distributed GPU clusters with ease
- **Job Scheduling**: Intelligent job scheduling across cluster nodes
- **Resource Management**: Track and optimize resource utilization
- **Health Monitoring**: Real-time health checks and alerting
- **CLI Tool**: Command-line interface for cluster operations
- **REST API**: FastAPI-based web API for integration
- **Metrics**: Prometheus-compatible metrics collection

## Project Structure

```
distributed-grid/
├── src/
│   └── distributed_grid/
│       ├── __init__.py              # Package exports
│       ├── main.py                  # Main entry point
│       ├── cli.py                   # CLI application (Typer)
│       ├── web.py                   # FastAPI web application
│       ├── api/                     # API layer
│       │   ├── __init__.py
│       │   └── v1/
│       │       ├── __init__.py
│       │       ├── router.py        # API router
│       │       └── endpoints/       # API endpoints
│       │           ├── __init__.py
│       │           ├── health.py
│       │           ├── clusters.py
│       │           ├── nodes.py
│       │           └── jobs.py
│       ├── config/                  # Configuration
│       │   ├── __init__.py
│       │   ├── models.py            # Pydantic models
│       │   └── settings.py          # Application settings
│       ├── core/                    # Core components
│       │   ├── __init__.py
│       │   ├── orchestrator.py
│       │   ├── executor.py
│       │   ├── ssh_manager.py
│       │   └── health_checker.py
│       ├── services/                # Business logic
│       │   ├── __init__.py
│       │   ├── cluster_service.py
│       │   ├── node_service.py
│       │   └── job_service.py
│       ├── orchestration/           # Job orchestration
│       │   ├── __init__.py
│       │   ├── job_scheduler.py
│       │   ├── resource_manager.py
│       │   └── task_executor.py
│       ├── monitoring/              # Monitoring & alerting
│       │   ├── __init__.py
│       │   ├── health_checker.py
│       │   ├── metrics_collector.py
│       │   └── alerting.py
│       ├── schemas/                 # Pydantic schemas
│       │   ├── __init__.py
│       │   ├── cluster.py
│       │   ├── node.py
│       │   └── job.py
│       └── utils/                   # Utilities
│           ├── __init__.py
│           ├── logging.py
│           ├── metrics.py
│           └── retry.py
├── tests/                           # Test suite
├── config/                          # Configuration files
├── docs/                            # Documentation
├── pyproject.toml                   # Poetry configuration
├── poetry.lock                      # Dependency lock file
├── Makefile                         # Development commands
└── README.md                        # This file
```

## Installation

### Prerequisites

- Python 3.11+
- Poetry (for dependency management)

### Setup

1. Clone the repository:
```bash
git clone https://github.com/ollieb89/orchestrator.git
cd orchestrator
```

2. Install dependencies:
```bash
make install
```

Or with Poetry directly:
```bash
poetry install
```

## Usage

### CLI

The CLI provides commands for managing clusters:

```bash
# Initialize a new cluster configuration
poetry run grid init --config config/my-cluster.yaml

# Validate a configuration
poetry run grid config config/my-cluster.yaml

# Provision nodes with environments
poetry run grid provision --config config/my-cluster.yaml

# Cluster management
poetry run grid cluster install    # Install Ray on all nodes
poetry run grid cluster start      # Start the Ray cluster
poetry run grid cluster stop       # Stop the Ray cluster
poetry run grid cluster status     # Check cluster status

# Start the orchestrator
poetry run grid start --config config/my-cluster.yaml

# Show version
poetry run grid version
```

### Web API

Start the web server:

```bash
poetry run distributed-grid-web
```

Or run directly:
```bash
poetry run python -m distributed_grid.web
```

The API will be available at `http://localhost:8000`

#### API Documentation

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### Python API

Use as a Python library:

```python
from distributed_grid import GridOrchestrator, ClusterConfig

# Load configuration
config = ClusterConfig.from_yaml("config/cluster_config.yaml")

# Initialize orchestrator
orchestrator = GridOrchestrator(config)

# Start the orchestrator
await orchestrator.start()
```

## Configuration

### Environment Variables

Create a `.env` file:

```env
# Application
DEBUG=true
ENVIRONMENT=development

# API
API_HOST=0.0.0.0
API_PORT=8000
API_ALLOWED_ORIGINS=["http://localhost:3000"]

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### Cluster Configuration

YAML configuration example:

```yaml
name: my-cluster
nodes:
  - name: node-01
    host: 192.168.1.100
    port: 22
    user: username
    gpu_count: 4
    memory_gb: 64
    tags: [gpu, cuda]
execution:
  default_nodes: 1
  default_gpus_per_node: 1
  timeout_seconds: 3600
  retry_attempts: 3
  working_directory: /tmp/grid
logging:
  level: INFO
  format: json
```

## Development

### Setup Development Environment

```bash
# Install development dependencies
make dev

# Run tests
make test

# Run linting
make lint

# Format code
make format

# Clean build artifacts
make clean
```

### Running Tests

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=src/distributed_grid

# Run specific test file
poetry run pytest tests/test_orchestrator.py
```

### Code Quality

- **Formatting**: Ruff
- **Linting**: Ruff + MyPy
- **Testing**: pytest with async support
- **Pre-commit**: Automatic hooks for quality checks

## Architecture

The project follows a layered architecture:

1. **API Layer**: FastAPI endpoints and CLI commands
2. **Service Layer**: Business logic and orchestration
3. **Core Layer**: Low-level cluster operations
4. **Infrastructure**: SSH, monitoring, utilities

Key components:

- **GridOrchestrator**: Main orchestrator for cluster operations
- **JobScheduler**: Schedules jobs across nodes
- **ResourceManager**: Tracks and allocates resources
- **HealthChecker**: Monitors node health
- **MetricsCollector**: Collects performance metrics

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Run the test suite
6. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Support

- Issues: https://github.com/ollieb89/orchestrator/issues
- Documentation: https://ollieb89.github.io/orchestrator
