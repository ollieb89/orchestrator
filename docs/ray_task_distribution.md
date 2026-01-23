# Ray Task Distribution Strategies

This guide explains how to effectively distribute tasks across your Ray cluster using the orchestrator.

## Overview

The orchestrator supports multiple scheduling strategies to optimize task placement across nodes:
- **SPREAD**: Distribute tasks evenly across all available nodes
- **LOAD_BALANCED**: Place tasks based on current node load
- **PERFORMANCE_OPTIMIZED**: Choose nodes with best performance characteristics
- **NODE_SPECIFIC**: Target specific nodes for task execution

## Quick Start

### 1. Basic Task Distribution

```python
import ray

# Simple task that will be distributed
@ray.remote
def compute_task(task_id: int):
    import socket
    node_ip = socket.gethostbyname(socket.gethostname())
    return {"task_id": task_id, "node": node_ip}

# Spread tasks across nodes
refs = []
for i in range(100):
    # Use SPREAD strategy for even distribution
    remote_fn = compute_task.options(scheduling_strategy="SPREAD")
    refs.append(remote_fn.remote(i))

results = ray.get(refs)
```

### 2. Node-Specific Placement

```python
# Target specific nodes
refs = []

# Submit to gpu1 (192.168.1.101)
for i in range(50):
    remote_fn = compute_task.options(resources={"node:192.168.1.101": 0.001})
    refs.append(remote_fn.remote(i))

# Submit to gpu2 (192.168.1.102)
for i in range(50, 100):
    remote_fn = compute_task.options(resources={"node:192.168.1.102": 0.001})
    refs.append(remote_fn.remote(i))
```

### 3. GPU Workload Distribution

```python
# GPU tasks automatically distribute across available GPUs
@ray.remote(num_gpus=1)
def gpu_training_step(batch_id: int):
    import torch
    
    if torch.cuda.is_available():
        device = torch.device("cuda")
        # Training logic here
        return f"Batch {batch_id} trained on GPU"
    return "No GPU available"

# Submit 6 GPU tasks - will distribute across 3 GPUs
refs = [gpu_training_step.remote(i) for i in range(6)]
results = ray.get(refs)
```

## CLI Commands

### Test Distribution Strategies

```bash
# Test spread strategy (default)
poetry run grid distribute test --strategy spread --tasks 100

# Test node-specific placement
poetry run grid distribute test --strategy node_specific --node gpu1 --tasks 50

# Check cluster status
poetry run grid distribute status
```

### Resource Sharing Integration

```bash
# Check resource sharing status
poetry run grid resource-sharing status --config config/my-cluster-enhanced.yaml

# Request resources for a node
poetry run grid resource-sharing request --node gpu-master --type cpu --amount 2.0 --priority high
```

## Advanced Patterns

### 1. Mixed Workload Distribution

```python
# CPU-intensive tasks with SPREAD
@ray.remote
def cpu_task(task_id):
    # CPU-heavy computation
    return result

cpu_refs = [
    cpu_task.options(scheduling_strategy="SPREAD").remote(i)
    for i in range(20)
]

# Memory-intensive tasks with LOAD_BALANCED
@ray.remote
def memory_task(task_id):
    # Memory-heavy computation
    return result

mem_refs = [
    memory_task.options(
        scheduling_strategy="LOAD_BALANCED",
        num_cpus=2.0
    ).remote(i)
    for i in range(10)
]

# GPU tasks (automatic placement)
@ray.remote(num_gpus=1)
def gpu_task(task_id):
    # GPU computation
    return result

gpu_refs = [gpu_task.remote(i) for i in range(3)]

# Wait for all tasks
all_results = ray.get(cpu_refs + mem_refs + gpu_refs)
```

### 2. Intelligent Scheduler Integration

```python
from distributed_grid.orchestration.intelligent_scheduler import (
    IntelligentScheduler,
    SchedulingRequest,
    SchedulingStrategy,
    ResourceRequirement,
)

# Create scheduler
scheduler = IntelligentScheduler(cluster_config, metrics_collector, resource_manager)

# Define task requirements
request = SchedulingRequest(
    task_id="my_task",
    requirements=ResourceRequirement(
        cpu_count=2.0,
        memory_mb=4096,
        gpu_count=1
    ),
    strategy=SchedulingStrategy.SPREAD,
    priority=TaskPriority.HIGH
)

# Schedule task
decision = await scheduler.schedule_task(request)
print(f"Task scheduled on {decision.node_id}")
```

### 3. Dynamic Load Balancing

```python
# Monitor cluster state and adjust strategy
@ray.remote
class LoadBalancer:
    def __init__(self):
        self.task_counts = {}
    
    def get_least_loaded_node(self, nodes):
        # Return node with fewest tasks
        counts = {node: self.task_counts.get(node, 0) for node in nodes}
        return min(counts.items(), key=lambda x: x[1])[0]
    
    def submit_task(self, task, nodes):
        target = self.get_least_loaded_node(nodes)
        self.task_counts[target] = self.task_counts.get(target, 0) + 1
        
        # Submit to specific node
        return task.options(resources={f"node:{target}": 0.001}).remote()

# Use the load balancer
balancer = LoadBalancer.remote()
nodes = ["192.168.1.101", "192.168.1.102"]

refs = []
for i in range(100):
    refs.append(balancer.submit_task.remote(compute_task, nodes))
```

## Best Practices

### 1. Choose the Right Strategy

- **SPREAD**: Best for many small, independent tasks
- **LOAD_BALANCED**: Good for varying task sizes
- **PERFORMANCE_OPTIMIZED**: Ideal for performance-critical tasks
- **NODE_SPECIFIC**: Use when tasks require specific resources

### 2. Resource Constraints

```python
# Specify resource requirements for better placement
@ray.remote(num_cpus=2, num_gpus=1, memory=4000 * 1024 * 1024)
def resource_intensive_task():
    # Task requiring 2 CPUs, 1 GPU, and 4GB RAM
    pass
```

### 3. Placement Groups

```python
# Create placement groups for multi-task workflows
from ray.util.placement_group import placement_group

pg = placement_group([{"CPU": 2, "GPU": 1}, {"CPU": 1}], strategy="STRICT_SPREAD")

@ray.remote
def task_in_pg():
    return "Task in placement group"

# Submit tasks to placement group
task1 = task_in_pg.options(
    placement_group=pg,
    placement_group_bundle_index=0
).remote()

task2 = task_in_pg.options(
    placement_group=pg,
    placement_group_bundle_index=1
).remote()
```

### 4. Monitoring and Debugging

```python
# Check task placement
import ray

def check_task_distribution():
    nodes = ray.nodes()
    for node in nodes:
        print(f"Node: {node['NodeManagerAddress']}")
        print(f"  Alive: {node['Alive']}")
        print(f"  Resources: {node['Resources']}")
        print(f"  Resource load: {node['ResourcesTotal']}")

# Get cluster resources
print(ray.cluster_resources())
print(ray.available_resources())
```

## Troubleshooting

### Tasks Not Distributing

1. Check if nodes are alive:
   ```bash
   poetry run grid distribute status
   ```

2. Verify Ray cluster connectivity:
   ```bash
   poetry run python scripts/validate_ray_cluster.py
   ```

3. Check resource constraints:
   - Are tasks requesting too many resources?
   - Are nodes properly registered?

### GPU Tasks Not Using GPUs

1. Verify GPU availability:
   ```python
   import ray
   print(ray.available_resources())
   ```

2. Check CUDA visibility:
   ```python
   @ray.remote
   def check_gpu():
       import torch
       return torch.cuda.is_available()
   
   result = ray.get(check_gpu.remote())
   ```

3. Ensure proper GPU resource request:
   ```python
   @ray.remote(num_gpus=1)  # Must specify GPU requirement
   def gpu_task():
       pass
   ```

### Performance Issues

1. Use appropriate scheduling strategy
2. Monitor resource utilization
3. Consider task batching for small tasks
4. Use placement groups for related tasks

## Examples

See `examples/ray_task_distribution.py` for complete working examples of all distribution patterns.
