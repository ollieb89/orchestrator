# Resource Boost Manager Guide

## Overview

The Resource Boost Manager is a powerful feature of the Distributed Grid Orchestrator that enables dynamic resource borrowing between nodes in a Ray cluster. It allows the master node to temporarily borrow CPU, GPU, and memory resources from worker nodes when additional resources are needed for intensive workloads.

## Key Features

- **Dynamic Resource Borrowing**: Request CPU, GPU, or memory resources from any worker node
- **Priority-based Allocation**: Support for LOW, NORMAL, HIGH, and CRITICAL priority levels
- **Automatic Resource Discovery**: Automatically finds nodes with available resources
- **Flexible Duration**: Set custom duration for resource boosts (default: 1 hour)
- **Resource Tracking**: Monitor active boosts and their expiration times
- **CLI Integration**: Easy-to-use command-line interface for managing boosts
- **Persistent Storage**: Resource boosts survive across CLI invocations and system restarts

## Architecture

The Resource Boost Manager consists of several components:

1. **ResourceBoostManager**: Core manager that handles boost requests and allocations
2. **ResourceMetricsCollector**: Monitors resource usage across the cluster
3. **ResourceSharingManager**: Manages the actual resource allocation and sharing
4. **ResourceBoostPersistence**: Provides file-based persistence for boost state
5. **CLI Commands**: Command-line interface for interacting with the system

## Persistence

Resource boosts are automatically persisted to disk in `~/.distributed_grid/resource_boosts.json`. This ensures that:

- Boosts survive across CLI invocations
- System restarts don't lose active boosts
- You can check boost status anytime
- Expired boosts are automatically cleaned up

The persistence file stores:
- Boost ID and allocation details
- Source and target nodes
- Resource type and amount
- Allocation and expiration timestamps
- Active status of each boost

## Getting Started

### Prerequisites

- Ray cluster running with at least 2 nodes
- Resource sharing enabled in cluster configuration
- Python 3.11+ with required dependencies

### Configuration

Enable resource sharing in your cluster configuration file (`config/my-cluster-enhanced.yaml`):

```yaml
resource_sharing:
  enabled: true
  policy: "balanced"  # Options: balanced, aggressive, conservative
  rebalance_interval: 30  # seconds
  pressure_thresholds:
    cpu:
      high: 0.8
      low: 0.3
    memory:
      high: 0.8
      low: 0.3
    gpu:
      high: 0.8
      low: 0.3
```

## CLI Commands

### 1. Request a Resource Boost

Request additional resources for a specific node:

```bash
# Request 2 CPU cores for gpu-master with high priority
poetry run grid boost request gpu-master cpu 2.0 --priority high

# Request 1 GPU for gpu-master for 30 minutes
poetry run grid boost request gpu-master gpu 1 --duration 1800

# Request 4 GB memory from a specific source node
poetry run grid boost request gpu-master memory 4.0 --source gpu2

# Request with normal priority (default)
poetry run grid boost request gpu-master cpu 4.0
```

#### Parameters

- `target_node`: Node that will receive the resources
- `resource_type`: Type of resource (cpu, gpu, memory)
- `amount`: Amount of resources to request
- `--priority`: Request priority (low, normal, high, critical)
- `--duration`: Duration in seconds (default: 3600 = 1 hour)
- `--source`: Preferred source node (optional)
- `--config`: Path to cluster configuration (default: config/my-cluster-enhanced.yaml)

### 2. Check Boost Status

View all active resource boosts:

```bash
# Show all active boosts
poetry run grid boost status

# Show boosts for a specific node
poetry run grid boost status --node gpu-master
```

The status command displays:
- Total number of active boosts
- Resources currently being boosted by type
- Detailed table of each active boost with:
  - Boost ID
  - Source and target nodes
  - Resource type and amount
  - Allocation time
  - Expiration time

### 3. Release a Resource Boost

Manually release an active boost before it expires:

```bash
poetry run grid boost release <boost-id>
```

You can find the boost ID from the status command. Boost IDs are typically displayed as a shortened version (first 8 characters) but you should use the full ID when releasing.

## Examples

### Example 1: CPU Boost for Intensive Computation

```bash
# Check current status
poetry run grid boost status

# Request additional CPU resources
poetry run grid boost request gpu-master cpu 4.0 --priority high --duration 1800

# Run your CPU-intensive task
python intensive_computation.py

# Release the boost early (optional)
poetry run grid boost release <boost-id>
```

### Example 2: GPU Boost for Machine Learning

```bash
# Request GPU for training
poetry run grid boost request gpu-master gpu 1 --priority critical --duration 3600

# The GPU is now available for Ray tasks
# Run your ML training script
python train_model.py

# Check boost status
poetry run grid boost status --node gpu-master
```

### Example 3: Memory Boost for Large Dataset Processing

```bash
# Request additional memory
poetry run grid boost request gpu-master memory 8.0 --source gpu2 --duration 7200

# Process large dataset
python process_large_dataset.py

# The boost will automatically expire after 2 hours
```

## Best Practices

### 1. Planning Resource Needs

- Estimate resource requirements before requesting boosts
- Use appropriate priority levels to avoid conflicts
- Set reasonable duration times to free resources for others

### 2. Monitoring and Cleanup

- Regularly check boost status with `grid boost status`
- Release boosts early if no longer needed
- Monitor the Ray dashboard for overall cluster utilization

### 3. Priority Guidelines

- **CRITICAL**: Emergency situations, production issues
- **HIGH**: Important batch jobs, time-sensitive tasks
- **NORMAL**: Regular workloads, development tasks
- **LOW**: Background tasks, non-urgent work

### 4. Resource Selection

- **CPU**: Good for parallel processing, data preprocessing
- **GPU**: Essential for ML training, GPU-accelerated computations
- **Memory**: Use for large datasets, in-memory processing

## Troubleshooting

### Common Issues

1. **"No nodes have sufficient available resources"**
   - Check cluster status with `grid cluster status`
   - Verify resource sharing is enabled
   - Try requesting smaller amounts or different resources

2. **"Target node not found in cluster"**
   - Verify node name matches cluster configuration
   - Check if the node is online and connected to Ray

3. **"Resource sharing not enabled"**
   - Enable resource sharing in configuration file
   - Restart the cluster after configuration changes

4. **"Boosts not persisting across CLI commands"**
   - Check if `~/.distributed_grid/resource_boosts.json` exists
   - Verify write permissions to the directory
   - Check logs for persistence errors

5. **"Persistence file corrupted"**
   - Delete the persistence file: `rm ~/.distributed_grid/resource_boosts.json`
   - Active boosts will be lost but system will recover

### Debug Commands

```bash
# Check cluster resources
poetry run grid cluster status

# Check resource sharing status
poetry run grid resource-sharing status

# Validate Ray cluster
poetry run python scripts/validate_ray_cluster.py
```

## API Reference

### ResourceBoostManager Class

#### Methods

- `request_boost(request: ResourceBoostRequest) -> Optional[str]`
  - Request a resource boost
  - Returns boost ID if successful

- `release_boost(boost_id: str) -> bool`
  - Release an active boost
  - Returns True if successful

- `get_active_boosts(target_node: Optional[str] = None) -> List[ResourceBoost]`
  - Get list of active boosts
  - Filter by target node if specified

- `get_boost_status() -> Dict[str, Any]`
  - Get overall boost status summary

### ResourceBoostRequest Dataclass

```python
@dataclass
class ResourceBoostRequest:
    target_node: str
    resource_type: ResourceType
    amount: float
    priority: AllocationPriority = AllocationPriority.NORMAL
    duration_seconds: Optional[float] = None
    preferred_source: Optional[str] = None
```

## Integration with Ray

The Resource Boost Manager integrates with Ray's resource management system:

1. **Custom Resources**: Creates custom Ray resources for each boost
2. **Placement Groups**: Uses placement groups for GPU boosts to ensure locality
3. **Automatic Cleanup**: Resources are automatically released when boosts expire

### Note on Ray Dynamic Resources

Ray has deprecated dynamic custom resources in newer versions. While the Resource Boost Manager still works for resource allocation and tracking, the Ray integration features may be limited in future Ray versions. Consider using placement groups directly for advanced resource management.

## Performance Considerations

- Resource boost requests add minimal overhead (~10-50ms)
- Monitoring runs at 30-second intervals by default
- Resource sharing has negligible impact on cluster performance
- Boost expiration is handled automatically without manual intervention

## Security Considerations

- Resource boosts are isolated within the Ray cluster
- No direct SSH access is required for resource allocation
- All resource requests are logged for auditing
- Access control follows Ray's security model

## Future Enhancements

Planned improvements include:

1. **Automatic Boost Suggestions**: AI-powered recommendations for resource boosts
2. **Advanced Scheduling**: Integration with Ray's scheduler for optimal placement
3. **Resource Forecasting**: Predictive resource allocation based on usage patterns
4. **Multi-Cluster Support**: Resource sharing across multiple Ray clusters

## Contributing

To contribute to the Resource Boost Manager:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request with detailed description

## Additional Resources

- [Ray Documentation](https://docs.ray.io/)
- [Distributed Grid Orchestrator README](../README.md)
- [Configuration Guide](configuration.md)
- [Troubleshooting Guide](troubleshooting.md)
