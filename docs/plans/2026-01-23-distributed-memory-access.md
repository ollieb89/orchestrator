# Distributed Memory Access Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable the master node (gpu-master) to effectively use the 12.5GB of distributed memory allocated across worker nodes (gpu1, gpu2).

**Architecture:** Implement two complementary approaches: (1) Automatic memory offloading using the existing enhanced offloading executor, and (2) Direct Ray remote object storage for explicit distributed memory access.

**Tech Stack:** Ray distributed computing, Python asyncio, existing orchestrator infrastructure, CLI commands

---

## Phase 1: Foundation - Verify Current Infrastructure

### Task 1: Test Current Memory Offloading Behavior

**Files:**
- Test: `tests/test_memory_offloading.py`
- Reference: `src/distributed_grid/orchestration/enhanced_offloading_executor.py`

**Step 1: Write test to verify memory-intensive tasks automatically offload**

```python
import pytest
import asyncio
import ray
from distributed_grid.orchestration.enhanced_offloading_executor import EnhancedOffloadingExecutor, OffloadingMode

@pytest.mark.asyncio
async def test_memory_intensive_task_offloading():
    """Test that memory-intensive tasks are automatically offloaded from master."""
    
    # Setup
    cluster_config = get_test_cluster_config()
    executor = EnhancedOffloadingExecutor(None, cluster_config, mode=OffloadingMode.DYNAMIC_BALANCING)
    
    # Create a memory-intensive recommendation
    from distributed_grid.orchestration.intelligent_scheduler import TaskRecommendation
    recommendation = TaskRecommendation(
        node_id="gpu-master",
        task_type="memory_intensive",
        estimated_memory_gb=5.0,  # Larger than master's available memory
        priority="high"
    )
    
    # Execute and verify it offloads to worker with memory allocation
    task_id = await executor.execute_offloading(recommendation)
    
    # Verify task was executed on worker node (not master)
    assert task_id is not None
    # Add verification of execution location
```

**Step 2: Run test to verify current behavior**

Run: `pytest tests/test_memory_offloading.py::test_memory_intensive_task_offloading -v`

Expected: Current behavior baseline (may fail if offloading not working)

**Step 3: Analyze results and document current state**

Document whether offloading is working and where memory-intensive tasks are executed.

---

## Phase 2: Option A - Enhanced Memory Offloading

### Task 2: Improve Memory Pressure Detection

**Files:**
- Modify: `src/distributed_grid/monitoring/resource_metrics.py:45-65`
- Test: `tests/test_resource_metrics.py`

**Step 1: Add memory pressure threshold detection**

```python
def get_memory_pressure_score(self, node_id: str) -> float:
    """Calculate memory pressure score (0-1, higher = more pressure)."""
    try:
        snapshot = self.node_snapshots.get(node_id)
        if not snapshot:
            return 0.5  # Unknown pressure
            
        # Calculate pressure based on available vs total memory
        memory_usage_percent = snapshot.memory_used / snapshot.memory_total
        
        # Pressure increases sharply above 80% usage
        if memory_usage_percent > 0.8:
            return min(1.0, (memory_usage_percent - 0.8) * 5)  # Scale to 0-1
        elif memory_usage_percent > 0.6:
            return (memory_usage_percent - 0.6) * 2.5  # Gentle pressure
        else:
            return 0.1  # Low pressure
            
    except Exception as e:
        logger.warning(f"Failed to calculate memory pressure for {node_id}: {e}")
        return 0.5
```

**Step 2: Add test for memory pressure detection**

```python
@pytest.mark.asyncio
async def test_memory_pressure_detection():
    collector = ResourceMetricsCollector(get_test_cluster_config())
    
    # Mock high memory usage
    collector.node_snapshots["gpu-master"] = ResourceSnapshot(
        node_id="gpu-master",
        cpu_count=16,
        cpu_used=14,
        memory_total=30.4 * 1024**3,  # 30.4GB in bytes
        memory_used=28.0 * 1024**3,   # 28GB used (92%)
        gpu_count=1,
        gpu_used=0,
        timestamp=datetime.now()
    )
    
    pressure = collector.get_memory_pressure_score("gpu-master")
    assert pressure > 0.8, "High memory usage should result in high pressure score"
```

**Step 3: Run tests**

Run: `pytest tests/test_resource_metrics.py::test_memory_pressure_detection -v`

Expected: PASS

**Step 4: Commit**

```bash
git add src/distributed_grid/monitoring/resource_metrics.py tests/test_resource_metrics.py
git commit -m "feat: add memory pressure detection for offloading decisions"
```

### Task 3: Integrate Memory Pressure into Offloading Decisions

**Files:**
- Modify: `src/distributed_grid/orchestration/enhanced_offloading_executor.py:150-180`
- Test: `tests/test_enhanced_offloading.py`

**Step 1: Modify offloading logic to consider memory pressure**

```python
async def _should_offload_for_memory(self, node_id: str, estimated_memory_gb: float) -> bool:
    """Determine if task should offload due to memory pressure."""
    
    # Get current memory pressure
    pressure = self.metrics_collector.get_memory_pressure_score(node_id)
    
    # Get available memory on this node
    snapshot = self.metrics_collector.node_snapshots.get(node_id)
    if not snapshot:
        return True  # Offload if we can't determine memory status
    
    available_memory_gb = (snapshot.memory_total - snapshot.memory_used) / (1024**3)
    
    # Offload if:
    # 1. Not enough available memory
    # 2. Memory pressure is high
    # 3. Task requires more memory than available
    should_offload = (
        estimated_memory_gb > available_memory_gb or
        pressure > 0.8 or
        available_memory_gb < 2.0  # Keep 2GB buffer
    )
    
    if should_offload:
        logger.info(f"Memory offloading recommended for {node_id}: "
                   f"need={estimated_memory_gb}GB, available={available_memory_gb:.1f}GB, "
                   f"pressure={pressure:.2f}")
    
    return should_offload
```

**Step 2: Add test for memory-based offloading decisions**

```python
@pytest.mark.asyncio
async def test_memory_based_offloading_decision():
    cluster_config = get_test_cluster_config()
    executor = EnhancedOffloadingExecutor(None, cluster_config)
    
    # Mock high memory pressure on master
    executor.metrics_collector.node_snapshots["gpu-master"] = ResourceSnapshot(
        node_id="gpu-master",
        cpu_count=16,
        cpu_used=8,
        memory_total=30.4 * 1024**3,
        memory_used=28.0 * 1024**3,  # High memory usage
        gpu_count=1,
        gpu_used=0,
        timestamp=datetime.now()
    )
    
    # Test that large memory tasks get offloaded
    should_offload = await executor._should_offload_for_memory("gpu-master", 5.0)
    assert should_offload, "Large memory tasks should offload under pressure"
    
    # Test that small tasks might stay local
    should_offload_small = await executor._should_offload_for_memory("gpu-master", 0.5)
    # This depends on your threshold logic
```

**Step 3: Run tests**

Run: `pytest tests/test_enhanced_offloading.py::test_memory_based_offloading_decision -v`

Expected: PASS

**Step 4: Commit**

```bash
git add src/distributed_grid/orchestration/enhanced_offloading_executor.py tests/test_enhanced_offloading.py
git commit -m "feat: integrate memory pressure into offloading decisions"
```

---

## Phase 3: Option C - Ray Remote Object Storage Interface

### Task 4: Create Distributed Memory Manager

**Files:**
- Create: `src/distributed_grid/memory/distributed_memory_manager.py`
- Test: `tests/test_distributed_memory_manager.py`

**Step 1: Create distributed memory manager class**

```python
import ray
import asyncio
from typing import Any, Optional, Dict
from dataclasses import dataclass
import structlog

logger = structlog.get_logger(__name__)

@dataclass
class MemoryObject:
    """Represents a stored object in distributed memory."""
    object_id: str
    object_ref: ray.ObjectRef
    size_bytes: int
    created_at: datetime
    node_hint: Optional[str] = None

class DistributedMemoryManager:
    """Manages distributed memory using Ray remote objects."""
    
    def __init__(self, cluster_config):
        self.cluster_config = cluster_config
        self._stored_objects: Dict[str, MemoryObject] = {}
        self._initialized = False
        
    async def initialize(self) -> None:
        """Initialize the memory manager."""
        if self._initialized:
            return
            
        # Ensure Ray is connected
        if not ray.is_initialized():
            ray.init(address="auto")
            
        self._initialized = True
        logger.info("Distributed memory manager initialized")
        
    async def store(self, key: str, data: Any, preferred_node: Optional[str] = None) -> bool:
        """Store data in distributed memory."""
        if not self._initialized:
            await self.initialize()
            
        try:
            # Create Ray object reference
            object_ref = ray.put(data)
            
            # Get size estimate (rough approximation)
            import sys
            size_bytes = sys.getsizeof(data)
            
            # Store metadata
            self._stored_objects[key] = MemoryObject(
                object_id=key,
                object_ref=object_ref,
                size_bytes=size_bytes,
                created_at=datetime.now(),
                node_hint=preferred_node
            )
            
            logger.info(f"Stored object {key} ({size_bytes} bytes) in distributed memory")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store object {key}: {e}")
            return False
            
    async def retrieve(self, key: str) -> Optional[Any]:
        """Retrieve data from distributed memory."""
        if key not in self._stored_objects:
            logger.warning(f"Object {key} not found in distributed memory")
            return None
            
        try:
            memory_obj = self._stored_objects[key]
            data = ray.get(memory_obj.object_ref)
            logger.debug(f"Retrieved object {key} from distributed memory")
            return data
            
        except Exception as e:
            logger.error(f"Failed to retrieve object {key}: {e}")
            return None
            
    async def delete(self, key: str) -> bool:
        """Delete object from distributed memory."""
        if key not in self._stored_objects:
            return False
            
        # Ray automatically cleans up object references when they go out of scope
        del self._stored_objects[key]
        logger.info(f"Deleted object {key} from distributed memory")
        return True
        
    async def list_objects(self) -> Dict[str, MemoryObject]:
        """List all stored objects."""
        return self._stored_objects.copy()
        
    async def get_stats(self) -> Dict[str, Any]:
        """Get memory manager statistics."""
        total_objects = len(self._stored_objects)
        total_bytes = sum(obj.size_bytes for obj in self._stored_objects.values())
        
        return {
            "total_objects": total_objects,
            "total_bytes": total_bytes,
            "total_mb": total_bytes / (1024**2),
            "objects": [
                {
                    "key": key,
                    "size_bytes": obj.size_bytes,
                    "size_mb": obj.size_bytes / (1024**2),
                    "created_at": obj.created_at.isoformat(),
                    "node_hint": obj.node_hint
                }
                for key, obj in self._stored_objects.items()
            ]
        }
```

**Step 2: Write comprehensive tests**

```python
import pytest
import asyncio
import ray
from distributed_grid.memory.distributed_memory_manager import DistributedMemoryManager

@pytest.mark.asyncio
async def test_store_and_retrieve():
    """Test basic store and retrieve operations."""
    manager = DistributedMemoryManager(get_test_cluster_config())
    await manager.initialize()
    
    # Store data
    test_data = {"message": "hello", "numbers": [1, 2, 3]}
    success = await manager.store("test_key", test_data)
    assert success, "Store operation should succeed"
    
    # Retrieve data
    retrieved = await manager.retrieve("test_key")
    assert retrieved == test_data, "Retrieved data should match stored data"

@pytest.mark.asyncio
async def test_store_large_dataset():
    """Test storing large datasets."""
    manager = DistributedMemoryManager(get_test_cluster_config())
    await manager.initialize()
    
    # Create large dataset (100MB)
    large_data = b"x" * (100 * 1024 * 1024)
    
    success = await manager.store("large_data", large_data)
    assert success, "Should be able to store large datasets"
    
    retrieved = await manager.retrieve("large_data")
    assert len(retrieved) == len(large_data), "Large data should be retrieved intact"

@pytest.mark.asyncio
async def test_nonexistent_key():
    """Test retrieving non-existent keys."""
    manager = DistributedMemoryManager(get_test_cluster_config())
    await manager.initialize()
    
    result = await manager.retrieve("nonexistent")
    assert result is None, "Non-existent keys should return None"
```

**Step 3: Run tests**

Run: `pytest tests/test_distributed_memory_manager.py -v`

Expected: All tests PASS

**Step 4: Commit**

```bash
git add src/distributed_grid/memory/distributed_memory_manager.py tests/test_distributed_memory_manager.py
git commit -m "feat: add distributed memory manager using Ray remote objects"
```

---

## Phase 4: CLI Integration

### Task 5: Add Memory Manager CLI Commands

**Files:**
- Modify: `src/distributed_grid/cli.py:1400-1500`
- Test: `tests/test_cli_memory_commands.py`

**Step 1: Add memory manager commands to CLI**

```python
@memory.command()
@click.argument("key")
@click.argument("data_file", type=click.Path(exists=True))
@click.option("--node", "-n", help="Preferred node for storage")
@click.option("--config", "-c", type=click.Path(exists=True, path_type=Path), default=Path("config/my-cluster-enhanced.yaml"))
def store(key: str, data_file: Path, node: str | None, config: Path) -> None:
    """Store file content in distributed memory."""
    setup_logging()

    async def _store():
        try:
            from distributed_grid.memory.distributed_memory_manager import DistributedMemoryManager
            
            # Read file content
            with open(data_file, 'rb') as f:
                data = f.read()
            
            cluster_config = ClusterConfig.from_yaml(config)
            manager = DistributedMemoryManager(cluster_config)
            await manager.initialize()
            
            success = await manager.store(key, data, preferred_node=node)
            
            if success:
                console.print(f"[green]✓[/green] Stored data as key: [bold]{key}[/bold]")
                console.print(f"Size: {len(data) / (1024**2):.2f} MB")
                if node:
                    console.print(f"Preferred node: [bold]{node}[/bold]")
            else:
                console.print(f"[red]✗[/red] Failed to store data")
                
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            import traceback
            console.print(traceback.formatexc())

    asyncio.run(_store())

@memory.command()
@click.argument("key")
@click.option("--output", "-o", type=click.Path(), help="Output file (default: stdout)")
@click.option("--config", "-c", type=click.Path(exists=True, path_type=Path), default=Path("config/my-cluster-enhanced.yaml"))
def retrieve(key: str, output: Path | None, config: Path) -> None:
    """Retrieve data from distributed memory."""
    setup_logging()

    async def _retrieve():
        try:
            from distributed_grid.memory.distributed_memory_manager import DistributedMemoryManager
            
            cluster_config = ClusterConfig.from_yaml(config)
            manager = DistributedMemoryManager(cluster_config)
            await manager.initialize()
            
            data = await manager.retrieve(key)
            
            if data is not None:
                if output:
                    with open(output, 'wb') as f:
                        if isinstance(data, str):
                            f.write(data.encode())
                        else:
                            f.write(data)
                    console.print(f"[green]✓[/green] Retrieved data to: [bold]{output}[/bold]")
                else:
                    # Print to stdout
                    if isinstance(data, bytes):
                        console.print(data.decode('utf-8', errors='replace'))
                    else:
                        console.print(data)
            else:
                console.print(f"[red]✗[/red] Key '{key}' not found")
                
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    asyncio.run(_retrieve())

@memory.command()
@click.option("--config", "-c", type=click.Path(exists=True, path_type=Path), default=Path("config/my-cluster-enhanced.yaml"))
def list_objects(config: Path) -> None:
    """List all objects in distributed memory."""
    setup_logging()

    async def _list_objects():
        try:
            from distributed_grid.memory.distributed_memory_manager import DistributedMemoryManager
            
            cluster_config = ClusterConfig.from_yaml(config)
            manager = DistributedMemoryManager(cluster_config)
            await manager.initialize()
            
            stats = await manager.get_stats()
            
            console.print(f"\nDistributed Memory Objects")
            console.print(f"Total Objects: {stats['total_objects']}")
            console.print(f"Total Size: {stats['total_mb']:.2f} MB\n")
            
            if stats['objects']:
                table = Table(title="Stored Objects")
                table.add_column("Key", style="cyan")
                table.add_column("Size (MB)", justify="right")
                table.add_column("Created At", justify="center")
                table.add_column("Node Hint", style="green")
                
                for obj in stats['objects']:
                    table.add_row(
                        obj['key'],
                        f"{obj['size_mb']:.2f}",
                        obj['created_at'][:19],  # Remove microseconds
                        obj['node_hint'] or "any"
                    )
                
                console.print(table)
            else:
                console.print("[dim]No objects stored[/dim]")
                
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    asyncio.run(_list_objects())
```

**Step 2: Add CLI tests**

```python
import pytest
import tempfile
import asyncio
from click.testing import CliRunner
from distributed_grid.cli import memory

def test_store_retrieve_cli():
    """Test CLI store and retrieve commands."""
    runner = CliRunner()
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("test data content")
        temp_file = f.name
    
    # Store data
    result = runner.invoke(memory, [
        'store', 'test_key', temp_file,
        '--config', 'tests/fixtures/test_cluster.yaml'
    ])
    assert result.exit_code == 0
    assert 'Stored data as key: test_key' in result.output
    
    # Retrieve data
    result = runner.invoke(memory, [
        'retrieve', 'test_key',
        '--config', 'tests/fixtures/test_cluster.yaml'
    ])
    assert result.exit_code == 0
    assert 'test data content' in result.output
```

**Step 3: Run tests**

Run: `pytest tests/test_cli_memory_commands.py -v`

Expected: PASS

**Step 4: Commit**

```bash
git add src/distributed_grid/cli.py tests/test_cli_memory_commands.py
git commit -m "feat: add distributed memory CLI commands"
```

---

## Phase 5: Integration Testing

### Task 6: End-to-End Integration Tests

**Files:**
- Create: `tests/test_distributed_memory_integration.py`
- Create: `examples/distributed_memory_demo.py`

**Step 1: Create comprehensive integration test**

```python
import pytest
import asyncio
import tempfile
from distributed_grid.memory.distributed_memory_manager import DistributedMemoryManager
from distributed_grid.orchestration.enhanced_offloading_executor import EnhancedOffloadingExecutor, OffloadingMode

@pytest.mark.asyncio
async def test_full_distributed_memory_workflow():
    """Test complete workflow: allocate memory, store data, retrieve from master."""
    
    cluster_config = get_test_cluster_config()
    
    # 1. Initialize distributed memory manager
    memory_manager = DistributedMemoryManager(cluster_config)
    await memory_manager.initialize()
    
    # 2. Store large dataset from master
    large_dataset = {
        'training_data': [i for i in range(1000000)],  # ~8MB
        'metadata': {'version': '1.0', 'source': 'test'}
    }
    
    success = await memory_manager.store('training_dataset', large_dataset)
    assert success, "Should successfully store large dataset"
    
    # 3. Verify data can be retrieved from master
    retrieved = await memory_manager.retrieve('training_dataset')
    assert retrieved == large_dataset, "Retrieved data should match original"
    
    # 4. Test offloading with memory pressure
    executor = EnhancedOffloadingExecutor(None, cluster_config, mode=OffloadingMode.DYNAMIC_BALANCING)
    
    # Mock high memory pressure on master
    executor.metrics_collector.node_snapshots["gpu-master"] = ResourceSnapshot(
        node_id="gpu-master",
        cpu_count=16,
        cpu_used=8,
        memory_total=30.4 * 1024**3,
        memory_used=28.0 * 1024**3,  # High memory usage
        gpu_count=1,
        gpu_used=0,
        timestamp=datetime.now()
    )
    
    # Create memory-intensive task
    from distributed_grid.orchestration.intelligent_scheduler import TaskRecommendation
    recommendation = TaskRecommendation(
        node_id="gpu-master",
        task_type="memory_intensive_computation",
        estimated_memory_gb=5.0,
        priority="high"
    )
    
    # Execute and verify it offloads
    task_id = await executor.execute_offloading(recommendation)
    assert task_id is not None, "Memory-intensive task should be offloaded"
    
    # 5. Verify distributed memory is still accessible after offloading
    still_retrieved = await memory_manager.retrieve('training_dataset')
    assert still_retrieved == large_dataset, "Data should remain accessible"
```

**Step 2: Create demo script**

```python
#!/usr/bin/env python3
"""
Distributed Memory Demo

This script demonstrates how to use the distributed memory system
to store and retrieve data across the cluster.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from distributed_grid.memory.distributed_memory_manager import DistributedMemoryManager
from distributed_grid.config.models import ClusterConfig

async def demo_distributed_memory():
    """Demonstrate distributed memory capabilities."""
    
    print("🚀 Distributed Memory Demo")
    print("=" * 50)
    
    # Initialize
    config_path = Path(__file__).parent.parent / "config" / "my-cluster-enhanced.yaml"
    cluster_config = ClusterConfig.from_yaml(config_path)
    manager = DistributedMemoryManager(cluster_config)
    await manager.initialize()
    
    print("✅ Distributed memory manager initialized")
    
    # Demo 1: Store and retrieve text data
    print("\n📝 Demo 1: Text Data")
    text_data = "This is a test message stored in distributed memory!"
    
    success = await manager.store("demo_text", text_data)
    print(f"Store success: {success}")
    
    retrieved = await manager.retrieve("demo_text")
    print(f"Retrieved: {retrieved}")
    assert retrieved == text_data
    
    # Demo 2: Store large binary data
    print("\n📊 Demo 2: Large Binary Data")
    binary_data = b"x" * (10 * 1024 * 1024)  # 10MB
    
    success = await manager.store("demo_binary", binary_data)
    print(f"Store 10MB binary data: {success}")
    
    retrieved_binary = await manager.retrieve("demo_binary")
    print(f"Retrieved {len(retrieved_binary)} bytes")
    assert len(retrieved_binary) == len(binary_data)
    
    # Demo 3: Store complex Python object
    print("\n🐍 Demo 3: Complex Python Object")
    complex_data = {
        "numbers": [1, 2, 3, 4, 5],
        "nested": {
            "a": "hello",
            "b": [10, 20, 30]
        },
        "metadata": {
            "version": "1.0",
            "created_at": "2026-01-23"
        }
    }
    
    success = await manager.store("demo_complex", complex_data)
    print(f"Store complex object: {success}")
    
    retrieved_complex = await manager.retrieve("demo_complex")
    print(f"Retrieved complex object: {retrieved_complex}")
    assert retrieved_complex == complex_data
    
    # Show stats
    print("\n📈 Memory Manager Statistics")
    stats = await manager.get_stats()
    print(f"Total objects: {stats['total_objects']}")
    print(f"Total size: {stats['total_mb']:.2f} MB")
    
    for obj in stats['objects']:
        print(f"  - {obj['key']}: {obj['size_mb']:.2f} MB")
    
    print("\n✅ Demo completed successfully!")

if __name__ == "__main__":
    asyncio.run(demo_distributed_memory())
```

**Step 3: Run integration tests**

Run: `pytest tests/test_distributed_memory_integration.py -v`

Expected: PASS

**Step 4: Run demo**

Run: `python examples/distributed_memory_demo.py`

Expected: Demo completes successfully, showing data storage and retrieval

**Step 5: Commit**

```bash
git add tests/test_distributed_memory_integration.py examples/distributed_memory_demo.py
git commit -m "feat: add distributed memory integration tests and demo"
```

---

## Phase 6: Documentation

### Task 7: Update Documentation

**Files:**
- Create: `docs/distributed_memory_usage.md`
- Modify: `README.md`

**Step 1: Create comprehensive usage documentation**

```markdown
# Distributed Memory Usage Guide

## Overview

The distributed memory system allows you to allocate memory across worker nodes and access it transparently from the master node.

## Quick Start

### 1. Allocate Memory

```bash
# Allocate 10GB on gpu2
poetry run grid memory allocate --size 10.0 --node gpu2
```

### 2. Store Data

```bash
# Store a file in distributed memory
poetry run grid memory store my_data /path/to/large_file.dat

# Store with preferred node
poetry run grid memory store dataset /path/to/dataset.csv --node gpu2
```

### 3. Retrieve Data

```bash
# Retrieve to stdout
poetry run grid memory retrieve my_data

# Retrieve to file
poetry run grid memory retrieve my_data --output downloaded_file.dat
```

### 4. List Objects

```bash
# List all stored objects
poetry run grid memory list-objects
```

### 5. Check Status

```bash
# Check memory allocations
poetry run grid memory status

# Check resource sharing status
poetry run grid resource-sharing status
```

## Programmatic Usage

### Distributed Memory Manager

```python
from distributed_grid.memory.distributed_memory_manager import DistributedMemoryManager
from distributed_grid.config.models import ClusterConfig

# Initialize
cluster_config = ClusterConfig.from_yaml("config/my-cluster-enhanced.yaml")
manager = DistributedMemoryManager(cluster_config)
await manager.initialize()

# Store data
await manager.store("my_key", large_dataset)

# Retrieve data
data = await manager.retrieve("my_key")
```

### Automatic Memory Offloading

The system automatically offloads memory-intensive tasks from the master node when:

- Memory usage exceeds 80%
- Available memory is less than 2GB
- Task requires more memory than available

```python
from distributed_grid.orchestration.enhanced_offloading_executor import EnhancedOffloadingExecutor

# The executor automatically handles offloading
executor = EnhancedOffloadingExecutor(ssh_manager, cluster_config, 
                                   mode=OffloadingMode.DYNAMIC_BALANCING)

# Large tasks will automatically be offloaded to workers with available memory
task_id = await executor.execute_offloading(memory_intensive_recommendation)
```

## Architecture

### Memory Allocation System

- **DistributedMemoryPool**: Manages memory blocks on worker nodes
- **ResourceSharingManager**: Handles resource allocation and sharing
- **EnhancedOffloadingExecutor**: Automatically offloads tasks based on memory pressure

### Ray Remote Objects

- **DistributedMemoryManager**: High-level interface for Ray object storage
- **Automatic Distribution**: Ray automatically distributes objects across the cluster
- **Transparent Access**: Objects accessible from any node in the cluster

## Best Practices

1. **Large Datasets**: Store datasets > 100MB in distributed memory
2. **Frequent Access**: Cache frequently accessed data with Ray objects
3. **Memory Pressure**: Let the system automatically offload when memory is high
4. **Node Preference**: Specify preferred nodes for data locality

## Troubleshooting

### Memory Not Showing on Master

The distributed memory is allocated on worker nodes, not the master. To use it:

1. Use the DistributedMemoryManager API
2. Let automatic offloading handle task placement
3. Access via Ray remote objects

### High Latency

Network latency is expected for distributed memory access. For best performance:

- Store data close to where it will be processed
- Use batch operations when possible
- Cache frequently accessed data locally
```

**Step 2: Update README with quick start**

```markdown
## Distributed Memory

Allocate and use memory across the cluster:

```bash
# Allocate memory
poetry run grid memory allocate --size 10.0 --node gpu2

# Store and retrieve data
poetry run grid memory store my_data /path/to/file
poetry run grid memory retrieve my_data

# Check status
poetry run grid memory status
```

See [docs/distributed_memory_usage.md](docs/distributed_memory_usage.md) for complete guide.
```

**Step 3: Commit**

```bash
git add docs/distributed_memory_usage.md README.md
git commit -m "docs: add distributed memory usage guide"
```

---

## Verification Checklist

### Phase 1: Foundation
- [ ] Current memory offloading behavior documented
- [ ] Test baseline established

### Phase 2: Enhanced Offloading
- [ ] Memory pressure detection implemented
- [ ] Offloading decisions consider memory pressure
- [ ] Tests pass for memory-based offloading

### Phase 3: Ray Remote Objects
- [ ] DistributedMemoryManager implemented
- [ ] Store/retrieve operations work
- [ ] Large datasets handled correctly
- [ ] All tests pass

### Phase 4: CLI Integration
- [ ] Store command works
- [ ] Retrieve command works
- [ ] List objects command works
- [ ] CLI tests pass

### Phase 5: Integration
- [ ] End-to-end workflow tested
- [ ] Demo script works
- [ ] Integration tests pass

### Phase 6: Documentation
- [ ] Usage guide created
- [ ] README updated
- [ ] Examples provided

### Final Verification
- [ ] Master node can effectively use distributed memory
- [ ] Both automatic offloading and manual storage work
- [ ] Performance is acceptable for real workloads
- [ ] Documentation is complete and accurate

---

**Total Estimated Time:** 2-3 days
**Key Success Metrics:**
- Memory-intensive tasks automatically offload from master
- Large datasets can be stored and retrieved from any node
- CLI commands provide easy access to distributed memory
- System handles 10GB+ allocations efficiently
