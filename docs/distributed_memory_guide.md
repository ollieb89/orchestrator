# Distributed Memory Guide

## Overview

Your cluster has **two complementary systems** for using worker node memory on gpu-master:

1. **Ray Placement Groups** (Current) - Reserves memory for Ray tasks
2. **Distributed Memory Pool** (New) - Transparent remote memory access like local RAM

## Current Status

✅ **Active Allocation**: 10GB from gpu2 → gpu-master  
- Source: gpu2 (27.6 GB free)
- Target: gpu-master (76.6% memory usage)
- Method: Ray placement group

## System 1: Ray Placement Groups (Already Working)

### What It Does
Reserves memory on worker nodes for Ray tasks running on gpu-master.

### How to Use

```python
import ray

# Tasks automatically use shared memory pool
@ray.remote(memory=5*1024**3)  # Request 5GB
def memory_intensive_task():
    import numpy as np
    large_array = np.zeros((1000000, 1000))
    return large_array.sum()

# Ray places this on gpu-master using gpu2's memory
result = ray.get(memory_intensive_task.remote())
```

### Manual Allocation

```bash
# Request 10GB of memory from workers for gpu-master
poetry run grid resource-sharing request \
  --node gpu-master \
  --type memory \
  --amount 10.0 \
  --priority high \
  --config config/my-cluster-enhanced.yaml

# Check status
poetry run grid resource-sharing status --config config/my-cluster-enhanced.yaml

# Release allocation
poetry run grid resource-sharing release <allocation_id>
```

### Automatic Rebalancing

Your config now triggers automatic memory requests when gpu-master exceeds **70% memory usage** (lowered from 80%).

**Configuration** (`config/my-cluster-enhanced.yaml`):
```yaml
execution:
  resource_sharing:
    enabled: true
    mode: dynamic_balancing
    policy: balanced
    rebalance_interval_seconds: 30
    thresholds:
      memory_pressure_high: 0.7  # Auto-request when >70%
```

## System 2: Distributed Memory Pool (New - Transparent Access)

### What It Does
Allows you to use worker memory **as if it were local RAM** - no Ray tasks required.

### How to Use

```python
import asyncio
from distributed_grid.orchestration.distributed_memory_pool import DistributedMemoryPool
from distributed_grid.config import load_cluster_config

async def use_remote_memory():
    # Initialize
    config = load_cluster_config("config/my-cluster-enhanced.yaml")
    pool = DistributedMemoryPool(config)
    await pool.initialize()
    
    # Allocate 5GB on gpu2
    block_id = await pool.allocate(5*1024**3, preferred_node="gpu2")
    
    # Write data (stored on gpu2, accessed from gpu-master)
    data = b"Your data here" * 1000000
    await pool.write(block_id, data)
    
    # Read data back
    retrieved = await pool.read(block_id, len(data))
    
    # Clean up
    await pool.deallocate(block_id)
    await pool.shutdown()

asyncio.run(use_remote_memory())
```

### Example: Numpy Arrays in Remote Memory

```python
import numpy as np

# Create large array
large_array = np.random.rand(10000, 10000)  # ~800MB
array_bytes = large_array.tobytes()

# Store on gpu2
block_id = await pool.allocate(len(array_bytes), preferred_node="gpu2")
await pool.write(block_id, array_bytes)

# Later: retrieve from gpu2
retrieved_bytes = await pool.read(block_id, len(array_bytes))
retrieved_array = np.frombuffer(retrieved_bytes, dtype=np.float64).reshape(10000, 10000)
```

### Run the Demo

```bash
poetry run python examples/distributed_memory_usage.py
```

## Comparison

| Feature | Ray Placement Groups | Distributed Memory Pool |
|---------|---------------------|------------------------|
| **Use Case** | Ray tasks/actors | Any Python code |
| **Transparency** | Requires Ray decorators | Direct memory access |
| **Performance** | Optimized for compute | Optimized for storage |
| **Persistence** | Task lifetime | Manual control |
| **Setup** | Automatic | Manual initialization |

## Best Practices

### When to Use Ray Placement Groups
- Running distributed computations
- Parallel task execution
- Temporary memory needs
- Automatic cleanup desired

### When to Use Distributed Memory Pool
- Large data caching
- Shared state across processes
- Non-Ray applications
- Fine-grained memory control

## Current Cluster Resources

**gpu-master** (Head):
- Memory: 30.4 GB total, 23.3 GB used (76.6%)
- Status: High memory pressure ⚠️

**gpu2** (Worker):
- Memory: 31.2 GB total, 3.6 GB used (11.6%)
- Available: **27.6 GB free** ✅

**gpu1** (Worker):
- Memory: 15.1 GB total, 5.1 GB used (34%)
- Available: **10 GB free** ✅

## Recommendations

### Immediate Actions

1. **Increase memory allocation** from gpu2:
   ```bash
   poetry run grid resource-sharing request \
     --node gpu-master \
     --type memory \
     --amount 15.0 \
     --priority high \
     --config config/my-cluster-enhanced.yaml
   ```

2. **Use distributed memory pool** for large datasets:
   ```python
   # Store large ML models on gpu2
   pool = DistributedMemoryPool(config)
   await pool.initialize()
   model_block = await pool.allocate(10*1024**3, preferred_node="gpu2")
   ```

### Long-term Improvements

1. **Enable background monitoring service** (TODO):
   - Continuous rebalancing
   - Automatic resource requests
   - Proactive memory management

2. **Implement memory pressure alerts**:
   - Notify when gpu-master exceeds 75%
   - Auto-request from workers
   - Graceful degradation

3. **Add memory compression**:
   - Compress data before storing remotely
   - Reduce network transfer overhead
   - Increase effective capacity

## Troubleshooting

### "No available nodes for memory allocation"
- Check workers are online: `poetry run grid distribute status`
- Verify Ray cluster: `ray status`
- Check worker memory: `poetry run grid resource-sharing status`

### "Failed to allocate memory block"
- Worker may be out of memory
- Try smaller allocation size
- Check worker node health

### Allocation not showing in status
- Allocations persist in `~/.distributed_grid/`
- Verify file permissions
- Check Ray dashboard: http://localhost:8265

## Next Steps

1. ✅ **Current**: 10GB allocated from gpu2 to gpu-master
2. 🔄 **Recommended**: Increase to 15-20GB based on your needs
3. 🚀 **Advanced**: Use distributed memory pool for transparent access
4. 📊 **Monitor**: Watch `poetry run grid resource-sharing status`

## Files Created

- `src/distributed_grid/orchestration/distributed_memory_pool.py` - Core implementation
- `examples/distributed_memory_usage.py` - Usage examples
- `config/my-cluster-enhanced.yaml` - Updated thresholds (70% → auto-request)
