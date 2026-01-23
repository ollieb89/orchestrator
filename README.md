# Distributed Grid

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![Code style](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Type checking](https://img.shields.io/badge/type%20checking-mypy-blue.svg)](https://mypy.readthedocs.io)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Optimized distributed GPU cluster orchestration tool built with Python 3.11+.

## Features

- **Distributed Execution**: Run commands across multiple GPU nodes simultaneously
- **Intelligent Scheduling**: Smart node selection based on GPU utilization and availability
- **Resource Boosting**: Dynamically borrow CPU, GPU, and memory resources from worker nodes
- **Health Monitoring**: Real-time cluster health checks and metrics collection
- **Modern CLI**: Beautiful command-line interface with rich output
- **Async Architecture**: Built for performance with asyncio and async patterns
- **Type Safety**: Full type annotations with mypy validation
- **Observability**: Prometheus metrics and structured logging

## Installation

### Using uv (Recommended)

```bash
# Clone the repository
git clone https://github.com/grid-team/distributed-grid.git
cd distributed-grid

# Install with uv
uv sync

# Activate the virtual environment
source .venv/bin/activate
```

### Using pip

```bash
# Clone the repository
git clone https://github.com/grid-team/distributed-grid.git
cd distributed-grid

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
```

## Quick Start

1. **Generate a configuration file**:
   ```bash
   grid config --output config/cluster_config.yaml
   ```

2. **Edit the configuration** to match your cluster:
   ```yaml
   cluster:
     name: "my-grid"
     nodes:
       - name: "gpu-node-01"
         host: "192.168.1.101"
         user: "grid"
         gpu_count: 4
         memory_gb: 64
   ```

3. **Initialize the cluster**:
   ```bash
   grid init --config config/cluster_config.yaml
   ```

4. **Check cluster status**:
   ```bash
   grid status --config config/cluster_config.yaml
   ```

5. **Run a command**:
   ```bash
   grid run "python train.py --epochs 100" --config config/cluster_config.yaml
   ```

## CLI Reference

### Commands

- `grid init` - Initialize the grid cluster
- `grid status` - Show cluster status and health
- `grid run <command>` - Execute a command on the cluster
- `grid config` - Generate a sample configuration file

### Resource Boost Commands

- `grid boost request <node> <resource> <amount>` - Request additional resources
- `grid boost release <boost-id>` - Release an active resource boost
- `grid boost status` - Show current resource boost status

#### Resource Boost Examples

```bash
# Request 2 CPU cores with high priority
grid boost request gpu-master cpu 2.0 --priority high

# Request 1 GPU for 30 minutes
grid boost request gpu-master gpu 1 --duration 1800

# Request 8GB memory from a specific worker
grid boost request gpu-master memory 8.0 --source gpu2

# Check active boosts
grid boost status

# Release a boost
grid boost release req_1234567890_gpu-master
```

### Options

- `--config, -c` - Path to configuration file (default: `config/cluster_config.yaml`)
- `--nodes, -n` - Number of nodes to use
- `--gpus, -g` - Number of GPUs per node
- `--verbose, -v` - Enable verbose output

For detailed documentation on resource boosting, see [Resource Boost Manager Guide](docs/resource_boost_manager_guide.md).

## Configuration

The cluster configuration is defined in a YAML file with the following structure:

```yaml
cluster:
  name: "my-grid"
  nodes:
    - name: "node-01"
      host: "192.168.1.101"
      port: 22
      user: "grid"
      gpu_count: 4
      memory_gb: 64
      ssh_key_path: "~/.ssh/id_rsa"
      tags: ["gpu", "cuda"]

execution:
  default_nodes: 1
  default_gpus_per_node: 1
  timeout_seconds: 3600
  retry_attempts: 3
  working_directory: "/tmp/grid"
  environment:
    CUDA_VISIBLE_DEVICES: "0,1,2,3"

logging:
  level: "INFO"
  format: "json"
  file_path: "logs/grid.log"
```

### Environment Variables

You can also configure the grid using environment variables:

```bash
export GRID_CLUSTER_NAME="my-grid"
export GRID_LOG_LEVEL="DEBUG"
export GRID_DEFAULT_NODES=2
export GRID_SSH_TIMEOUT=30
```

See `.env.example` for all available variables.

## Development

### Setup Development Environment

```bash
# Install development dependencies
uv sync --group dev

# Install pre-commit hooks
pre-commit install
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/distributed_grid

# Run specific test file
uv run pytest tests/test_config.py
```

### Code Quality

```bash
# Format code
uv run ruff format .

# Lint code
uv run ruff check .

# Type checking
uv run mypy src

# Run all quality checks
uv run ruff check . && uv run mypy src && uv run pytest
```

### Project Structure

```
distributed-grid/
├── src/distributed_grid/
│   ├── __init__.py
│   ├── cli.py              # Command-line interface
│   ├── config/
│   │   ├── __init__.py
│   │   └── models.py       # Configuration models
│   ├── core/
│   │   ├── __init__.py
│   │   ├── orchestrator.py # Main orchestration logic
│   │   ├── executor.py     # Command execution
│   │   ├── ssh_manager.py  # SSH connection management
│   │   └── health_checker.py # Health monitoring
│   └── utils/
│       ├── __init__.py
│       ├── logging.py      # Logging utilities
│       ├── metrics.py      # Metrics collection
│       └── retry.py        # Retry utilities
├── tests/
│   ├── __init__.py
│   ├── conftest.py         # Pytest configuration
│   ├── test_config.py
│   ├── test_core.py
│   ├── test_utils.py
│   └── test_cli.py
├── config/
│   └── cluster_config.yaml # Example configuration
├── docs/
│   └── ...                 # Documentation
├── pyproject.toml
├── README.md
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml
└── Makefile
```

## Architecture

The distributed grid follows a modular architecture:

- **CLI Layer**: User interface and command handling
- **Core Layer**: Orchestration, execution, and health monitoring
- **Config Layer**: Configuration management and validation
- **Utils Layer**: Shared utilities for logging, metrics, and retry logic

### Key Components

1. **GridOrchestrator**: Main orchestrator that coordinates all operations
2. **SSHManager**: Manages SSH connections to cluster nodes
3. **GridExecutor**: Executes commands across the cluster
4. **HealthChecker**: Monitors node health and GPU utilization
5. **MetricsCollector**: Collects and exposes Prometheus metrics

## Monitoring

### Metrics

The grid exposes Prometheus metrics on port 8000 by default:

- `grid_commands_total` - Total commands executed
- `grid_command_duration_seconds` - Command execution duration
- `grid_node_online` - Node online status
- `grid_gpu_utilization_percent` - GPU utilization
- `grid_active_tasks` - Number of active tasks

### Logging

Structured logging with JSON format:

```json
{
  "timestamp": "2024-01-01T12:00:00Z",
  "level": "INFO",
  "logger": "distributed_grid.core.orchestrator",
  "message": "Command executed successfully",
  "node": "gpu-node-01",
  "command": "python train.py",
  "duration": 45.2
}
```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes and add tests
4. Run the test suite: `uv run pytest`
5. Check code quality: `uv run ruff check . && uv run mypy src`
6. Commit your changes: `git commit -m 'Add amazing feature'`
7. Push to the branch: `git push origin feature/amazing-feature`
8. Open a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- 📖 [Documentation](https://distributed-grid.readthedocs.io)
- 🐛 [Issue Tracker](https://github.com/grid-team/distributed-grid/issues)
- 💬 [Discussions](https://github.com/grid-team/distributed-grid/discussions)

## Acknowledgments

- Built with [Ray](https://ray.io/) for distributed computing
- CLI powered by [Typer](https://typer.tiangolo.com/) and [Rich](https://rich.readthedocs.io/)
- Configuration with [Pydantic](https://pydantic-docs.helpmanual.io/)
- Async patterns with [asyncio](https://docs.python.org/3/library/asyncio.html)