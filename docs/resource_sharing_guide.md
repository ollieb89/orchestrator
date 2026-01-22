# Resource Sharing Guide

The orchestrator now supports resource sharing across nodes, allowing the master node to leverage idle resources on worker nodes when needed.

## Overview

Resource sharing enables:
- Dynamic resource discovery across the cluster
- Automatic offloading of jobs to nodes with available capacity
- Efficient utilization of cluster resources
- Priority-based resource allocation

## Architecture

### Components

1. **ResourceSharingManager**: Manages resource offers and allocations
2. **ResourceSharingProtocol**: Handles communication with worker nodes
3. **Worker Agent**: Light-weight agent installed on worker nodes for monitoring
4. **Resource Offers**: Advertisements of available resources from workers
5. **Resource Requests**: Requests for resources from the master node

### Flow

1. Worker nodes monitor their resource usage
2. When resources are idle (below thresholds), they offer them to the master
3. Master node maintains a pool of available resource offers
4. When jobs need resources, master requests from the pool
5. Jobs are offloaded to nodes with available resources
6. Resources are released when jobs complete

## Configuration

Add to your `cluster_config.yaml`:

```yaml
resource_sharing:
  enabled: true
  check_interval: 60  # seconds
  offer_expiry: 300   # seconds
  max_offers_per_node: 5
  thresholds:
    gpu_utilization_max: 20.0    # GPU must be below 20% utilization
    gpu_memory_min_mb: 1024.0    # At least 1GB free GPU memory
    memory_percent_max: 50.0     # Memory must be below 50% used
    memory_min_gb: 2.0           # At least 2GB free memory
    cpu_percent_max: 30.0        # CPU must be below 30% utilization
    cpu_min_cores: 1.0           # At least 1 CPU core free
```

## CLI Usage

### Run a command with shared resources

```bash
# Request 1 GPU for a training job
grid run-shared --resource-type gpu --amount 1 --priority high python train.py

# Request 4GB of memory for data processing
grid run-shared --resource-type memory --amount 4 --priority medium python process_data.py

# Request 2 CPU cores for a parallel task
grid run-shared --resource-type cpu --amount 2 --priority low python parallel_task.py

# Specify preferred nodes
grid run-shared -r gpu -a 1 -n gpu1 -n gpu2 python train.py
```

### Check resource sharing status

```bash
grid shared-status
```

This shows:
- Current resource offers from worker nodes
- Active resource allocations

## Programmatic Usage

```python
from distributed_grid.core import GridOrchestrator
from distributed_grid.config import ClusterConfig
from distributed_grid.orchestration.resource_sharing import ResourceType

# Load configuration
config = ClusterConfig.from_yaml("config/cluster_config.yaml")
orchestrator = GridOrchestrator(config)

# Initialize
await orchestrator.initialize()

# Request resources and run job
result = await orchestrator.run_with_shared_resources(
    command="python train.py",
    resource_type=ResourceType.GPU,
    amount=1,
    priority="high",
    job_id="training_001"
)

# Check status
status = await orchestrator.get_shared_resource_status()
print(f"Available offers: {status['offers']}")
print(f"Active allocations: {status['allocations']}")

# Cleanup
await orchestrator.shutdown()
```

## Resource Types

### GPU
- Requests GPU devices with available memory
- Automatically sets `CUDA_VISIBLE_DEVICES`
- Monitors GPU utilization and memory usage

### Memory
- Requests memory in GB
- Ensures sufficient free memory on the node
- Useful for memory-intensive tasks

### CPU
- Requests CPU cores
- Uses `taskset` to pin processes to cores
- Good for CPU-bound parallel tasks

## Priority Levels

- **urgent**: Highest priority, preempts if possible
- **high**: High priority, gets first choice of resources
- **medium**: Default priority, fair-share allocation
- **low**: Best-effort, uses leftover resources

## Best Practices

1. **Set appropriate thresholds**: Configure thresholds based on your workload patterns
2. **Use priorities**: Tag critical jobs with higher priorities
3. **Monitor usage**: Use `shared-status` to track resource utilization
4. **Clean up resources**: Always release resources when done (handled automatically)
5. **Plan for failures**: Jobs should handle resource unavailability gracefully

## Troubleshooting

### No resource offers available
- Check if worker nodes are online: `grid status`
- Verify thresholds are not too strict
- Ensure worker agents are installed

### Jobs failing to execute
- Check if resources were actually allocated
- Verify the command works on the target node
- Check logs for detailed error messages

### High resource usage
- Adjust thresholds to be more restrictive
- Monitor for runaway jobs
- Consider implementing resource limits

## Example Use Cases

### 1. Dynamic Training Job Offloading

```python
# When main node is overloaded, offload to workers
if local_gpu_utilization > 80:
    result = await orchestrator.run_with_shared_resources(
        command="python train_model.py",
        resource_type=ResourceType.GPU,
        amount=1,
        priority="high"
    )
```

### 2. Batch Processing with Available Memory

```python
# Process large datasets when memory is available
result = await orchestrator.run_with_shared_resources(
    command="python process_large_dataset.py",
    resource_type=ResourceType.MEMORY,
    amount=8,  # Need 8GB
    priority="low"
)
```

### 3. Parallel Computation

```python
# Run parallel tasks on multiple nodes
tasks = []
for i in range(4):
    task = orchestrator.run_with_shared_resources(
        command=f"python compute_task.py --task-id {i}",
        resource_type=ResourceType.CPU,
        amount=2,
        priority="medium"
    )
    tasks.append(task)

results = await asyncio.gather(*tasks)
```

## Security Considerations

- Worker agents run with the same user as SSH connection
- Resource isolation is handled at the process level
- Jobs run in isolated working directories
- No privileged operations are performed

## Future Enhancements

- Support for custom resource types (TPUs, FPGAs)
- Resource reservation and scheduling
- Cost-based resource selection
- Integration with Kubernetes
- Advanced fairness algorithms
