#!/usr/bin/env python3
"""Demo script for distributed memory pool functionality."""

import asyncio
import tempfile
import os
from pathlib import Path

from distributed_grid.orchestration.distributed_memory_pool import DistributedMemoryPool
from distributed_grid.config import ClusterConfig
import ray


async def demo_distributed_memory():
    """Demonstrate distributed memory pool capabilities."""
    print("🚀 Distributed Memory Pool Demo")
    print("=" * 50)
    
    # Initialize Ray
    ray.init(address="auto", namespace="distributed_memory_pool")
    
    try:
        # Load cluster configuration
        config_path = Path("config/my-cluster-enhanced.yaml")
        cluster_config = ClusterConfig.from_yaml(config_path)
        
        # Initialize memory pool
        memory_pool = DistributedMemoryPool(cluster_config)
        await memory_pool.initialize(persistent=True)
        
        print("\n1. Allocating memory blocks...")
        
        # Allocate a 10MB block
        block1_id = await memory_pool.allocate(10 * 1024 * 1024)  # 10MB
        print(f"   ✓ Allocated block: {block1_id} (10MB)")
        
        # Allocate a 5MB block on specific node
        block2_id = await memory_pool.allocate(5 * 1024 * 1024, preferred_node="gpu2")
        print(f"   ✓ Allocated block: {block2_id} (5MB on gpu2)")
        
        print("\n2. Writing data to blocks...")
        
        # Create test data
        test_data1 = b"Hello, Distributed Memory! " * 100000  # ~3MB
        test_data2 = b"This is stored on gpu2! " * 100000  # ~2.5MB
        
        # Write data to blocks
        success1 = await memory_pool.write(block1_id, test_data1)
        success2 = await memory_pool.write(block2_id, test_data2)
        
        print(f"   ✓ Wrote {len(test_data1)} bytes to {block1_id}")
        print(f"   ✓ Wrote {len(test_data2)} bytes to {block2_id}")
        
        print("\n3. Reading data from blocks...")
        
        # Read data back
        read_data1 = await memory_pool.read(block1_id, len(test_data1))
        read_data2 = await memory_pool.read(block2_id, len(test_data2))
        
        print(f"   ✓ Read {len(read_data1)} bytes from {block1_id}")
        print(f"   ✓ Read {len(read_data2)} bytes from {block2_id}")
        
        # Verify data integrity
        assert read_data1 == test_data1, "Data mismatch in block1!"
        assert read_data2 == test_data2, "Data mismatch in block2!"
        print("   ✓ Data integrity verified!")
        
        print("\n4. Partial reads with offset...")
        
        # Read partial data
        partial_data = await memory_pool.read(block1_id, 100, offset=50)
        print(f"   ✓ Read 100 bytes from offset 50: {partial_data[:50]}...")
        
        print("\n5. Memory pool statistics...")
        
        # Get statistics
        stats = await memory_pool.get_stats()
        print(f"   Total blocks: {stats['total_blocks']}")
        print(f"   Active nodes: {len(stats['nodes'])}")
        
        for node_id, node_stats in stats['nodes'].items():
            print(f"   Node {node_id}: {node_stats['blocks_count']} blocks, "
                  f"{node_stats['total_mb']:.2f} MB")
        
        print("\n6. Demonstrating shared memory pattern...")
        
        # Multiple writes to the same block
        shared_block_id = await memory_pool.allocate(1024)  # 1KB shared block
        print(f"   ✓ Allocated shared block: {shared_block_id}")
        
        # Process A writes
        msg_a = b"Process A was here!"
        await memory_pool.write(shared_block_id, msg_a, offset=0)
        print(f"   ✓ Process A wrote: {msg_a.decode()}")
        
        # Process B reads
        read_msg = await memory_pool.read(shared_block_id, len(msg_a), offset=0)
        print(f"   ✓ Process B read: {read_msg.decode()}")
        
        # Process B writes at different offset
        msg_b = b"Process B too!"
        await memory_pool.write(shared_block_id, msg_b, offset=len(msg_a))
        
        # Read combined data
        combined = await memory_pool.read(shared_block_id, len(msg_a) + len(msg_b))
        print(f"   ✓ Combined message: {combined.decode()}")
        
        print("\n7. Cleanup...")
        
        # Deallocate blocks
        await memory_pool.deallocate(block1_id)
        await memory_pool.deallocate(block2_id)
        await memory_pool.deallocate(shared_block_id)
        print("   ✓ Deallocated all blocks")
        
        print("\n✅ Demo completed successfully!")
        
        # Show usage examples
        print("\n📖 CLI Usage Examples:")
        print("# Allocate a 10MB block")
        print("poetry run grid memory allocate 10485760")
        print()
        print("# Store a file in a new block")
        print("poetry run grid memory store mydata /path/to/file.txt")
        print()
        print("# Store in existing block")
        print("poetry run grid memory store moredata /path/to/file2.txt --block-id <block_id>")
        print()
        print("# Retrieve data")
        print("poetry run grid memory retrieve <block_id> --output output.txt")
        print()
        print("# List all blocks")
        print("poetry run grid memory list-objects")
        print()
        print("# Deallocate a block")
        print("poetry run grid memory deallocate <block_id>")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        ray.shutdown()


if __name__ == "__main__":
    asyncio.run(demo_distributed_memory())
