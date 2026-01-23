# Quick Start: Distributed Memory Pool

## 5-Minute Setup

### Prerequisites

- Ray cluster running (see main README)
- Poetry installed
- Cluster configured in `config/my-cluster-enhanced.yaml`

### Step 1: Verify Cluster Status

```bash
poetry run grid distribute status
```

You should see all nodes as "Alive".

### Step 2: Allocate Your First Memory Block

```bash
# Allocate 5GB on gpu2
poetry run grid memory allocate --size 5.0 --node gpu2
```

Output:
```
✓ Allocated 5.00 GB
Block ID: block_0_gpu2
```

**Save the Block ID** - you'll need it to access the memory.

### Step 3: View Memory Pool Status

```bash
poetry run grid memory stats
```

You'll see your allocation:
```
Distributed Memory Pool Statistics
Total Blocks: 1

Node Memory Usage
┏━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Node   ┃ Blocks ┃ Total Memory ┃
┡━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━┩
│ gpu2   │      1 │     5.00 GB  │
└────────┴────────┴──────────────┘
```

### Step 4: Use the Memory in Python

Create `test_memory.py`:

```python
import asyncio
from distributed_grid.orchestration.distributed_memory_pool import DistributedMemoryPool
from distributed_grid.config import load_cluster_config

async def main():
    # Initialize
    config = load_cluster_config("config/my-cluster-enhanced.yaml")
    pool = DistributedMemoryPool(config)
    await pool.initialize()
    
    # Your block ID from Step 2
    block_id = "block_0_gpu2"
    
    # Write data
    data = b"Hello from gpu-master!"
    await pool.write(block_id, data)
    print(f"✓ Wrote {len(data)} bytes to {block_id}")
    
    # Read data back
    retrieved = await pool.read(block_id, len(data))
    print(f"✓ Read back: {retrieved.decode()}")
    
    await pool.shutdown()

asyncio.run(main())
```

Run it:
```bash
poetry run python test_memory.py
```

### Step 5: Clean Up

```bash
poetry run grid memory deallocate block_0_gpu2
```

## Common Use Cases

### Use Case 1: Cache Large Dataset

```python
from distributed_grid.utils.memory_helpers import DistributedMemoryHelper
import numpy as np

async def cache_dataset():
    helper = DistributedMemoryHelper(pool)
    
    # Load large dataset (e.g., 10GB)
    dataset = np.random.rand(100000, 10000)
    
    # Store on gpu2
    block_id = await helper.store_numpy_array(dataset, preferred_node="gpu2")
    print(f"Cached dataset: {block_id}")
    
    # Later: retrieve
    cached_dataset = await helper.retrieve_numpy_array(block_id)
    print(f"Retrieved dataset shape: {cached_dataset.shape}")
```

### Use Case 2: Offload ML Model Weights

```python
async def offload_model():
    helper = DistributedMemoryHelper(pool)
    
    # Large model weights
    model_weights = {
        'encoder': np.random.rand(5000, 5000),
        'decoder': np.random.rand(5000, 5000),
    }
    
    # Store on gpu2
    block_id = await helper.store_object(model_weights, preferred_node="gpu2")
    print(f"Model weights stored: {block_id}")
    
    # Free local memory
    del model_weights
    
    # Later: load when needed
    weights = await helper.retrieve_object(block_id)
    print(f"Loaded {len(weights)} layers")
```

### Use Case 3: Automatic Resource Sharing

```bash
# Request 10GB memory allocation for gpu-master from workers
poetry run grid resource-sharing request \
  --node gpu-master \
  --type memory \
  --amount 10.0 \
  --priority high

# Check allocation status
poetry run grid resource-sharing status
```

This creates a Ray placement group that automatically makes the memory available to Ray tasks on gpu-master.

## Next Steps

1. **Read the full guide**: [Distributed Memory Guide](distributed_memory_guide.md)
2. **Explore CLI commands**: [CLI Reference](distributed_memory_cli_reference.md)
3. **Run examples**: `poetry run python examples/distributed_memory_usage.py`
4. **Check resource sharing**: `poetry run grid resource-sharing status`

## Troubleshooting

### Can't allocate memory

```bash
# Check available memory on workers
poetry run grid resource-sharing status

# Try smaller allocation
poetry run grid memory allocate --size 2.0
```

### Block not found

```bash
# List all blocks
poetry run grid memory list-blocks

# Verify block ID
```

### Pool not initialized

Make sure Ray cluster is running:
```bash
ray status
```

## Performance Tips

- **Allocate once, use many times**: Reuse blocks instead of allocating/deallocating frequently
- **Choose the right node**: Use `--node` to place data close to processing
- **Monitor usage**: Run `grid memory stats` regularly
- **Clean up**: Always deallocate when done

## Help

```bash
# Get help on memory commands
poetry run grid memory --help

# Get help on specific command
poetry run grid memory allocate --help
```
