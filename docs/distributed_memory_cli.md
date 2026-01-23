# Distributed Memory CLI Guide

## Overview
The distributed memory CLI provides commands to manage memory blocks across your Ray cluster, enabling the master node to store and retrieve data from worker node memory.

## Commands

### 1. Allocate Memory
```bash
poetry run grid memory allocate <size_in_bytes> [--node <node_name>]
```
Allocate a new distributed memory block.

**Example:**
```bash
# Allocate 10MB on any worker node
poetry run grid memory allocate 10485760

# Allocate 5MB on gpu2 specifically
poetry run grid memory allocate 5242880 --node gpu2
```

### 2. Store Data
```bash
poetry run grid memory store <key> <file_path> [--block-id <id>] [--offset <n>]
```
Store file content in distributed memory.

**Examples:**
```bash
# Store in a new block (auto-allocates)
poetry run grid memory store mymodel model_weights.pt

# Store in existing block at specific offset
poetry run grid memory store checkpoint checkpoint.pt --block-id block_0_gpu2 --offset 1024
```

### 3. Retrieve Data
```bash
poetry run grid memory retrieve <block_id> [--output <file>] [--size <n>] [--offset <n>]
```
Retrieve data from a memory block.

**Examples:**
```bash
# Retrieve to stdout (shows preview)
poetry run grid memory retrieve block_0_gpu2

# Retrieve to file
poetry run grid memory retrieve block_0_gpu2 --output retrieved_model.pt

# Retrieve specific chunk
poetry run grid memory retrieve block_0_gpu2 --size 1048576 --offset 0
```

### 4. List Memory Blocks
```bash
poetry run grid memory list-objects
```
Show all allocated memory blocks and their status.

### 5. Deallocate Memory
```bash
poetry run grid memory deallocate <block_id>
```
Release a memory block.

## Use Cases

### ML Model Storage
Store large model weights on worker nodes with high memory:
```bash
# Allocate 10GB on gpu2
poetry run grid memory allocate 10737418240 --node gpu2

# Store model weights
poetry run grid memory store "llama-7b" llama_weights.pt --block-id block_0_gpu2
```

### Data Processing Pipeline
Use blocks as shared workspace:
```bash
# Allocate workspace
poetry run grid memory allocate 104857600

# Process A writes results
poetry run grid memory store results part1.csv --block-id block_0_gpu1 --offset 0

# Process B appends more data
poetry run grid memory store results part2.csv --block-id block_0_gpu1 --offset 50000
```

### Inter-node Communication
Share data between processes on different nodes:
```bash
# Node A stores data
poetry run grid memory store shared data.json

# Node B retrieves data
poetry run grid memory retrieve block_0_gpu2 --output data.json
```

## Tips

1. **Block IDs**: After allocation, note the block ID for future operations
2. **Persistence**: Memory blocks persist across CLI invocations when using `persistent=True`
3. **Size Management**: Always check block size before writing to avoid overflow
4. **Node Selection**: Use `--node` to target specific workers with available memory
5. **Cleanup**: Deallocate blocks when done to free worker memory

## Integration with Python API

```python
from distributed_grid.orchestration.distributed_memory_pool import DistributedMemoryPool

# Initialize
memory_pool = DistributedMemoryPool(cluster_config)
await memory_pool.initialize(persistent=True)

# Use block ID from CLI
block_id = "block_0_gpu2"  # From `grid memory allocate`
data = await memory_pool.read(block_id, size_you_need)
```
