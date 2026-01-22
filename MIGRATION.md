# Migration Guide: From Legacy Scripts to New Architecture

This guide helps you migrate from the old standalone scripts to the new Distributed Grid architecture.

## Overview of Changes

The new architecture provides:
- Unified CLI with all functionality
- REST API for programmatic access
- Better error handling and logging
- Type safety and validation
- Async/await support

## Command Mapping

### Old → New Commands

| Old Command | New Command | Notes |
|-------------|-------------|-------|
| `python grid_setup.py` | `poetry run grid provision` | Sets up node environments |
| `python cluster_manager.py install` | `poetry run grid cluster install` | Install Ray on nodes |
| `python cluster_manager.py start` | `poetry run grid cluster start` | Start Ray cluster |
| `python cluster_manager.py stop` | `poetry run grid cluster stop` | Stop Ray cluster |
| `python cluster_manager.py status` | `poetry run grid cluster status` | Check cluster status |
| `./grid_executor.sh "cmd"` | `poetry run grid execute --command "cmd"` | Execute on best node |
| `python grid_balancer.py` | Integrated into resource manager | Automatic node selection |

## Step-by-Step Migration

### 1. Update Your Workflow

**Old way:**
```bash
# Setup cluster
python grid_setup.py
python cluster_manager.py install
python cluster_manager.py start

# Run workloads
./grid_executor.sh "python train.py"
```

**New way:**
```bash
# Setup cluster
poetry install  # Install dependencies
poetry run grid init  # Create config
poetry run grid provision  # Setup nodes
poetry run grid cluster install  # Install Ray
poetry run grid cluster start  # Start cluster

# Run workloads
poetry run grid execute --command "python train.py"
```

### 2. Configuration Changes

**Old way** (hardcoded in scripts):
```python
# grid_setup.py
CONFIG = {
    "nodes": ["gpu1", "gpu2"],
    "remote_workspace_root": "~/grid_workspace",
    "pip_packages": ["torch", "tensorflow"],
}
```

**New way** (YAML configuration):
```yaml
# config/cluster_config.yaml
name: my-cluster
nodes:
  - name: gpu1
    host: 192.168.1.100
    user: myuser
    gpu_count: 4
    memory_gb: 64
execution:
  default_nodes: 1
  working_directory: /tmp/grid
```

### 3. Programmatic Access

**Old way** (direct imports):
```python
from cluster_manager import ClusterManager
manager = ClusterManager()
manager.start()
```

**New way** (use the orchestrator):
```python
from distributed_grid import GridOrchestrator, ClusterConfig

config = ClusterConfig.from_yaml("config/cluster_config.yaml")
orchestrator = GridOrchestrator(config)
await orchestrator.start()
```

### 4. API Integration

The new architecture provides a REST API:

```bash
# Submit a job via API
curl -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "training-job",
    "command": "python train.py",
    "cluster_id": "my-cluster",
    "gpu_count": 1
  }'
```

## Deprecated Features

The following have been deprecated and will be removed in v0.3.0:
- `grid_balancer.py` - Use ResourceManager instead
- `grid_executor.sh` - Use `grid execute` command
- Direct script execution - Use the unified CLI

## Getting Help

For more information:
- Read the [main documentation](README_NEW.md)
- Check the [examples](examples/)
- Run `poetry run grid --help` for CLI help

## Troubleshooting

### Issue: Can't find old scripts
**Solution**: Use the new `grid` CLI commands instead

### Issue: Configuration format changed
**Solution**: Run `poetry run grid init` to create a new config template

### Issue: Missing functionality
**Solution**: Check if it's available via the REST API or create an issue on GitHub
