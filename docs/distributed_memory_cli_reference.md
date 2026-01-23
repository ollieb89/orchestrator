# Distributed Memory CLI Reference

## Overview

The distributed memory pool provides transparent access to worker node memory from the master node, enabling you to use remote RAM as if it were local.

## CLI Commands

### Memory Pool Commands

All memory pool commands are under the `grid memory` group.

#### Allocate Memory

Allocate a block of distributed memory on a worker node.

```bash
poetry run grid memory allocate --size <GB> [--node <node_name>]
```

**Options:**
- `--size, -s`: Size in GB to allocate (required)
- `--node, -n`: Preferred node for allocation (optional, auto-selects if not specified)
- `--config, -c`: Path to cluster config (default: `config/my-cluster-enhanced.yaml`)

**Examples:**

```bash
# Allocate 5GB on any available worker
poetry run grid memory allocate --size 5.0

# Allocate 10GB specifically on gpu2
poetry run grid memory allocate --size 10.0 --node gpu2

# Allocate with custom config
poetry run grid memory allocate --size 8.0 --config config/my-cluster.yaml
```

**Output:**
```
✓ Allocated 5.00 GB
Block ID: block_0_worker1
Node: worker1
```

#### Deallocate Memory

Free a previously allocated memory block.

```bash
poetry run grid memory deallocate <block_id>
```

**Arguments:**
- `block_id`: The block ID returned from allocation

**Examples:**

```bash
# Deallocate a specific block
poetry run grid memory deallocate block_0_worker1
```

**Output:**
```
✓ Deallocated block: block_0_worker1
```

#### View Statistics

Show distributed memory pool statistics across all nodes.

```bash
poetry run grid memory stats
```

**Options:**
- `--config, -c`: Path to cluster config (default: `config/my-cluster-enhanced.yaml`)

**Examples:**

```bash
# View memory pool stats
poetry run grid memory stats
```

**Output:**
```
Distributed Memory Pool Statistics
Total Blocks: 3

Node Memory Usage
┏━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Node   ┃ Blocks ┃ Total Memory ┃
┡━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━┩
│ gpu1   │      2 │    10.50 MB  │
│ gpu2   │      1 │     5.00 MB  │
└────────┴────────┴──────────────┘
```

#### List Allocated Blocks

List all currently allocated memory blocks.

```bash
poetry run grid memory list-blocks
```

**Options:**
- `--config, -c`: Path to cluster config (default: `config/my-cluster-enhanced.yaml`)

**Examples:**

```bash
# List all blocks
poetry run grid memory list-blocks
```

**Output:**
```
Allocated Memory Blocks
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━┓
┃ Block ID        ┃ Node   ┃ Size     ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━┩
│ block_0_gpu1    │ gpu1   │ 5.00 MB  │
│ block_1_gpu2    │ gpu2   │ 10.00 MB │
└─────────────────┴────────┴──────────┘
```

### Resource Sharing Commands

Commands for Ray placement group-based resource sharing.

#### Request Resources

Request shared resources from worker nodes.

```bash
poetry run grid resource-sharing request \
  --node <node_id> \
  --type <cpu|gpu|memory> \
  --amount <amount> \
  [--priority <low|normal|high|critical>]
```

**Options:**
- `--node, -n`: Node ID to request resources for (required)
- `--type, -t`: Resource type: cpu, gpu, or memory (required)
- `--amount, -a`: Amount of resource to request (required)
- `--priority, -p`: Priority level (default: normal)
- `--config, -c`: Path to cluster config

**Examples:**

```bash
# Request 10GB memory for gpu-master
poetry run grid resource-sharing request \
  --node gpu-master \
  --type memory \
  --amount 10.0 \
  --priority high

# Request 4 CPUs for gpu-master
poetry run grid resource-sharing request \
  --node gpu-master \
  --type cpu \
  --amount 4.0
```

#### View Resource Sharing Status

Show current resource sharing status including allocations and node utilization.

```bash
poetry run grid resource-sharing status
```

**Options:**
- `--config, -c`: Path to cluster config

**Output:**
```
Resource Sharing Orchestrator Status
Sharing Enabled: Yes
Initialized: Yes

Active Allocations
┏━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━┓
┃ ID       ┃ Source ┃ Target     ┃ Resource ┃ Amount ┃
┡━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━┩
│ alloc_17 │ gpu2   │ gpu-master │ MEMORY   │     10 │
└──────────┴────────┴────────────┴──────────┴────────┘
```

#### Release Resources

Release a previously allocated resource.

```bash
poetry run grid resource-sharing release <allocation_id>
```

**Arguments:**
- `allocation_id`: The allocation ID from the status command

**Examples:**

```bash
# Release an allocation
poetry run grid resource-sharing release alloc_1769173486_gpu-master
```

## Python API

### Using Distributed Memory Pool

```python
from distributed_grid.orchestration.distributed_memory_pool import DistributedMemoryPool
from distributed_grid.config import load_cluster_config

async def use_distributed_memory():
    # Initialize
    config = load_cluster_config("config/my-cluster-enhanced.yaml")
    pool = DistributedMemoryPool(config)
    await pool.initialize()
    
    # Allocate 5GB on gpu2
    block_id = await pool.allocate(5*1024**3, preferred_node="gpu2")
    
    # Write data
    data = b"Your data here" * 1000000
    await pool.write(block_id, data)
    
    # Read data back
    retrieved = await pool.read(block_id, len(data))
    
    # Clean up
    await pool.deallocate(block_id)
    await pool.shutdown()
```

### Using Helper Utilities

```python
from distributed_grid.utils.memory_helpers import DistributedMemoryHelper
import numpy as np

async def use_memory_helpers():
    # Create helper
    helper = DistributedMemoryHelper(pool)
    
    # Store Python object
    obj = {"key": "value", "data": [1, 2, 3]}
    block_id = await helper.store_object(obj, preferred_node="gpu2")
    
    # Retrieve object
    retrieved_obj = await helper.retrieve_object(block_id)
    
    # Store NumPy array
    array = np.random.rand(1000, 1000)
    array_block = await helper.store_numpy_array(array, preferred_node="gpu2")
    
    # Retrieve array
    retrieved_array = await helper.retrieve_numpy_array(array_block)
    
    # Cache large data
    await helper.cache_large_data("my_cache_key", large_data)
    cached = await helper.get_cached_data("my_cache_key")
```

### Using Resource Sharing Orchestrator

```python
from distributed_grid.orchestration.resource_sharing_orchestrator import ResourceSharingOrchestrator
from distributed_grid.core.ssh_manager import SSHManager

async def use_orchestrator():
    # Initialize
    cluster_config = load_cluster_config("config/my-cluster-enhanced.yaml")
    ssh_manager = SSHManager(cluster_config.nodes)
    orchestrator = ResourceSharingOrchestrator(cluster_config, ssh_manager)
    await orchestrator.initialize()
    
    # Allocate distributed memory
    block_id = await orchestrator.allocate_distributed_memory(
        size_bytes=10*1024**3,
        preferred_node="gpu2"
    )
    
    # Write data
    await orchestrator.write_distributed_memory(block_id, b"data")
    
    # Read data
    data = await orchestrator.read_distributed_memory(block_id, 4)
    
    # Get stats
    stats = await orchestrator.get_distributed_memory_stats()
    
    # Clean up
    await orchestrator.deallocate_distributed_memory(block_id)
    await orchestrator.stop()
```

## Common Workflows

### Workflow 1: Allocate Memory for Heavy Processing

```bash
# 1. Check current memory usage
poetry run grid resource-sharing status

# 2. Allocate 15GB on gpu2 for gpu-master
poetry run grid memory allocate --size 15.0 --node gpu2

# 3. Use the allocated memory in your application
# (Block ID: block_0_gpu2)

# 4. Monitor usage
poetry run grid memory stats

# 5. When done, deallocate
poetry run grid memory deallocate block_0_gpu2
```

### Workflow 2: Cache Large Datasets

```python
from distributed_grid.utils.memory_helpers import DistributedMemoryHelper

async def cache_workflow():
    helper = DistributedMemoryHelper(pool)
    
    # Load large dataset
    large_dataset = load_large_dataset()
    
    # Cache on gpu2
    await helper.cache_large_data(
        "training_data",
        large_dataset,
        preferred_node="gpu2"
    )
    
    # Later: retrieve from cache
    dataset = await helper.get_cached_data("training_data")
    
    # When done
    await helper.clear_cache("training_data")
```

### Workflow 3: Store ML Model Weights

```python
import numpy as np

async def store_model_weights():
    helper = DistributedMemoryHelper(pool)
    
    # Large model weights
    weights = {
        'layer1': np.random.rand(1000, 1000),
        'layer2': np.random.rand(1000, 1000),
        'layer3': np.random.rand(1000, 1000),
    }
    
    # Store each layer on gpu2
    block_ids = {}
    for layer_name, layer_weights in weights.items():
        block_id = await helper.store_numpy_array(
            layer_weights,
            preferred_node="gpu2"
        )
        block_ids[layer_name] = block_id
    
    # Later: load weights
    loaded_weights = {}
    for layer_name, block_id in block_ids.items():
        loaded_weights[layer_name] = await helper.retrieve_numpy_array(block_id)
```

## Troubleshooting

### "Distributed memory pool is not initialized"

**Cause**: Pool not initialized before use.

**Solution**:
```python
await pool.initialize()
```

### "No available nodes for memory allocation"

**Cause**: All worker nodes are offline or out of memory.

**Solution**:
1. Check cluster status: `poetry run grid distribute status`
2. Verify Ray cluster: `ray status`
3. Check worker memory: `poetry run grid resource-sharing status`

### "Failed to allocate memory block"

**Cause**: Worker node doesn't have enough free memory.

**Solution**:
1. Check available memory: `poetry run grid memory stats`
2. Try smaller allocation size
3. Specify different node with `--node`

### Block ID not found

**Cause**: Block was deallocated or never existed.

**Solution**:
1. List current blocks: `poetry run grid memory list-blocks`
2. Verify block ID spelling
3. Check if block was already deallocated

## Performance Tips

1. **Batch Operations**: Allocate larger blocks and reuse them rather than many small allocations
2. **Node Selection**: Use `--node` to place data close to where it will be processed
3. **Compression**: Compress data before storing to reduce memory usage and network transfer
4. **Cleanup**: Always deallocate blocks when done to free memory for other tasks
5. **Monitoring**: Regularly check `grid memory stats` to track usage

## Integration with Ray Tasks

```python
import ray

@ray.remote(memory=5*1024**3)
def process_with_shared_memory():
    # This task will use the shared memory pool
    # Ray automatically uses allocated resources
    import numpy as np
    large_array = np.zeros((10000, 10000))
    return large_array.sum()

# Ray places this on gpu-master using gpu2's memory
result = ray.get(process_with_shared_memory.remote())
```

## See Also

- [Distributed Memory Guide](distributed_memory_guide.md) - Comprehensive guide
- [Resource Sharing Documentation](intelligent_resource_sharing.md) - Resource sharing system
- [Ray Task Distribution](ray_task_distribution.md) - Task distribution patterns
