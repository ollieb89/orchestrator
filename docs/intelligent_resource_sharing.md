# Intelligent Resource Sharing System

## Overview

The Intelligent Resource Sharing System enables dynamic resource allocation and sharing across the Ray cluster, allowing the master node to actively utilize worker resources when needed and rebalancing resources based on real-time demand.

## Architecture

### Core Components

1. **ResourceMetricsCollector** - Monitors real-time resource usage across all nodes
2. **ResourceSharingManager** - Manages resource allocation and sharing policies
3. **IntelligentScheduler** - Makes cross-node resource allocation decisions
4. **EnhancedOffloadingExecutor** - Executes tasks using shared resources dynamically
5. **ResourceSharingOrchestrator** - Coordinates all components

## Key Features

### Dynamic Resource Sharing
- Master node can borrow CPU, memory, and GPU resources from workers
- Workers can share excess resources when underutilized
- Automatic resource reclamation when tasks complete

### Intelligent Scheduling
- Multiple scheduling strategies (local-first, best-fit, load-balanced, etc.)
- Priority-based resource allocation
- Confidence scoring for placement decisions

### Adaptive Rebalancing
- Continuous monitoring of resource pressure
- Proactive resource requests based on trends
- Configurable thresholds and policies

## Configuration

### Enable Resource Sharing

Add to your cluster configuration (`config/my-cluster.yaml`):

```yaml
execution:
  resource_sharing:
    enabled: true
    mode: dynamic_balancing  # offload_only, share_and_offload, dynamic_balancing
    policy: balanced  # conservative, balanced, aggressive, predictive
    rebalance_interval_seconds: 30
    monitoring_interval_seconds: 10
    thresholds:
      cpu_pressure_high: 0.8
      cpu_pressure_low: 0.3
      memory_pressure_high: 0.8
      memory_pressure_low: 0.3
      gpu_pressure_high: 0.8
      gpu_pressure_low: 0.3
      excess_threshold: 0.2
```

### Node-Specific Settings

```yaml
nodes:
- name: gpu-master
  resource_sharing:
    can_share: true
    max_share_cpu: 4
    max_share_memory_gb: 16
    max_share_gpu: 0
    priority: 1.0
```

## Usage

### Basic Usage

```python
from distributed_grid.orchestration.resource_sharing_orchestrator import ResourceSharingOrchestrator

# Create orchestrator
orchestrator = ResourceSharingOrchestrator(cluster_config, ssh_manager)

# Initialize and start
await orchestrator.initialize()
await orchestrator.start()

# Get cluster status
status = await orchestrator.get_cluster_status()

# Request resources
request_id = await orchestrator.request_resources(
    node_id="gpu-master",
    resource_type="cpu",
    amount=2.0,
    priority="high",
    duration_minutes=30
)

# Get resource snapshots
snapshots = orchestrator.get_node_resource_snapshots()
```

### Enhanced Offloading

```python
from distributed_grid.orchestration.enhanced_offloading_executor import EnhancedOffloadingExecutor

# Create enhanced executor
executor = EnhancedOffloadingExecutor(
    ssh_manager,
    cluster_config,
    mode=OffloadingMode.DYNAMIC_BALANCING
)

# Execute with intelligent resource sharing
task_id = await executor.execute_offloading(recommendation)
```

## API Reference

### ResourceSharingOrchestrator

#### Methods

- `initialize()` - Initialize all components
- `start()` - Start the orchestrator
- `stop()` - Stop all components
- `get_cluster_status()` - Get comprehensive cluster status
- `request_resources(node_id, resource_type, amount, priority, duration)` - Request shared resources
- `release_resources(allocation_id)` - Release allocated resources
- `get_node_resource_snapshots()` - Get current resource snapshots

### ResourceMetricsCollector

#### Methods

- `start()` - Start monitoring
- `stop()` - Stop monitoring
- `get_all_latest_snapshots()` - Get latest snapshots for all nodes
- `get_resource_trend(node_id, resource_type)` - Get resource usage trends
- `get_cluster_summary()` - Get cluster-wide resource summary

### ResourceSharingManager

#### Methods

- `request_resource(node_id, resource_type, amount, priority, duration)` - Request resources
- `release_resource(allocation_id)` - Release resources
- `get_resource_status()` - Get sharing status

### IntelligentScheduler

#### Methods

- `schedule_task(request)` - Schedule a task
- `complete_task(task_id)` - Mark task as completed
- `get_scheduling_status()` - Get scheduling status

## Monitoring and Metrics

### Resource Pressure Scores

Each node has a pressure score (0-1) calculated from:
- CPU utilization (30% weight)
- Memory utilization (30% weight)
- GPU utilization (40% weight)

### Resource Trends

The system tracks trends over:
- 5 minutes - Short-term changes
- 15 minutes - Medium-term patterns
- 1 hour - Long-term trends

### Performance Metrics

- Task execution time
- Resource efficiency
- Allocation success rate
- Rebalancing frequency

## Best Practices

### Configuration Tips

1. **Threshold Tuning**: Adjust thresholds based on your workload patterns
2. **Policy Selection**: 
   - Use `conservative` for production stability
   - Use `balanced` for general workloads
   - Use `aggressive` for maximum utilization
   - Use `predictive` for bursty workloads

### Resource Allocation

1. **Request appropriate amounts**: Don't request more than needed
2. **Set reasonable durations**: Shorter durations allow better sharing
3. **Use priorities wisely**: Reserve `critical` for essential tasks

### Monitoring

1. **Monitor pressure scores**: High pressure indicates need for more resources
2. **Track trends**: Predict future resource needs
3. **Watch allocation rates**: Low rates may indicate configuration issues

## Troubleshooting

### Common Issues

1. **Resources not being shared**
   - Check if `resource_sharing.enabled` is true
   - Verify nodes have excess resources above threshold
   - Check node priorities and policies

2. **High resource pressure**
   - Increase resource thresholds
   - Add more nodes to cluster
   - Check for resource leaks

3. **Tasks not scheduling**
   - Verify resource requirements are realistic
   - Check affinity/anti-affinity settings
   - Review scheduling strategy

### Debug Commands

```bash
# Check cluster status
poetry run python -c "
import asyncio
from examples.intelligent_sharing_demo import ResourceSharingDemo
demo = ResourceSharingDemo('config/my-cluster-enhanced.yaml')
asyncio.run(demo._demo_cluster_status())
"

# Monitor resources
poetry run python -c "
import asyncio
from examples.intelligent_sharing_demo import ResourceSharingDemo
demo = ResourceSharingDemo('config/my-cluster-enhanced.yaml')
asyncio.run(demo._demo_resource_monitoring())
"
```

## Examples

See `examples/intelligent_sharing_demo.py` for a comprehensive demo showing:
- Cluster status overview
- Real-time resource monitoring
- Resource request and allocation
- Intelligent task scheduling
- Dynamic load balancing

## Testing

Run the test suite:

```bash
# Run all tests
poetry run pytest tests/test_intelligent_resource_sharing.py -v

# Run specific test class
poetry run pytest tests/test_intelligent_resource_sharing.py::TestResourceSharingManager -v

# Run with coverage
poetry run pytest tests/test_intelligent_resource_sharing.py --cov=distributed_grid.monitoring.resource_metrics --cov=distributed_grid.orchestration.resource_sharing_manager
```

## Performance Considerations

### Resource Overhead

- Monitoring adds ~1% CPU overhead per node
- Rebalancing runs every 30 seconds (configurable)
- Resource allocation uses Ray placement groups

### Scaling Limits

- Tested up to 100 nodes
- Supports 1000+ concurrent allocations
- Memory usage scales with node count

### Optimization Tips

1. Adjust monitoring intervals based on needs
2. Use appropriate history sizes for trend analysis
3. Tune rebalancing frequency for your workload

## Future Enhancements

- Machine learning-based prediction
- Multi-cluster resource sharing
- Advanced scheduling algorithms
- GPU memory sharing
- Network-aware placement
