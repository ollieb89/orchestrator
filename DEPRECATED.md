# Deprecation Notice

The following files have been deprecated and will be removed in a future version:

## Deprecated Files

### `grid_balancer.py`
- **Reason**: Functionality is now provided by the `ResourceManager` and monitoring components
- **Replacement**: Use `distributed_grid.orchestration.ResourceManager` for node selection
- **Status**: Deprecated - will be removed in v0.3.0

### `grid_executor.sh`
- **Reason**: Shell script replaced by Python-based CLI and TaskExecutor
- **Replacement**: Use `grid` CLI commands or `distributed_grid.orchestration.TaskExecutor`
- **Status**: Deprecated - will be removed in v0.3.0

## Migration Guide

### Old Workflow
```bash
# Using grid_executor.sh
./grid_executor.sh "python script.py"

# Using grid_balancer.py
python grid_balancer.py
```

### New Workflow
```bash
# Using the new CLI
poetry run grid execute --command "python script.py"

# Or use the web API
curl -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{"command": "python script.py", "cluster_id": "my-cluster"}'
```

## Rationale

The new architecture provides:
- Better error handling and logging
- Type safety with Pydantic models
- REST API for programmatic access
- Proper resource management and monitoring
- Async/await support for better performance

## Timeline

- **v0.2.0** - Files marked as deprecated (current)
- **v0.3.0** - Files will be removed
- **v0.4.0** - All deprecated functionality fully integrated into new architecture
