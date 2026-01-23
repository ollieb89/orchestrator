"""Example: Using distributed memory pool for transparent remote memory access."""

import asyncio
import numpy as np
import ray
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from distributed_grid.config import load_cluster_config
from distributed_grid.orchestration.distributed_memory_pool import DistributedMemoryPool


async def main():
    """Demonstrate distributed memory usage."""
    
    # Load cluster config
    config_path = Path(__file__).parent.parent / "config" / "my-cluster-enhanced.yaml"
    cluster_config = load_cluster_config(config_path)
    
    # Initialize Ray
    if not ray.is_initialized():
        ray.init(address="auto")
    
    # Create distributed memory pool
    print("🚀 Initializing distributed memory pool...")
    pool = DistributedMemoryPool(cluster_config)
    await pool.initialize()
    
    # Show initial stats
    stats = await pool.get_stats()
    print(f"\n📊 Memory Pool Stats:")
    print(f"   Total blocks: {stats['total_blocks']}")
    for node_id, node_stats in stats['nodes'].items():
        print(f"   {node_id}: {node_stats['total_mb']:.2f} MB allocated")
    
    # Example 1: Allocate 1GB on a worker node
    print("\n💾 Allocating 1GB on worker node...")
    block_id = await pool.allocate(1024**3, preferred_node="gpu2")
    
    if block_id:
        print(f"   ✓ Allocated block: {block_id}")
        
        # Example 2: Write data to remote memory
        print("\n✍️  Writing data to remote memory...")
        test_data = b"Hello from gpu-master! " * 1000
        success = await pool.write(block_id, test_data)
        print(f"   {'✓' if success else '✗'} Write {'succeeded' if success else 'failed'}")
        
        # Example 3: Read data back
        print("\n📖 Reading data from remote memory...")
        read_data = await pool.read(block_id, len(test_data))
        if read_data == test_data:
            print("   ✓ Data verified successfully!")
        else:
            print("   ✗ Data mismatch!")
        
        # Example 4: Use with numpy arrays
        print("\n🔢 Storing numpy array in remote memory...")
        large_array = np.random.rand(1000, 1000)  # ~8MB
        array_bytes = large_array.tobytes()
        
        array_block = await pool.allocate(len(array_bytes), preferred_node="gpu2")
        if array_block:
            await pool.write(array_block, array_bytes)
            print(f"   ✓ Stored {len(array_bytes)/(1024**2):.2f} MB array on gpu2")
            
            # Read it back
            retrieved_bytes = await pool.read(array_block, len(array_bytes))
            retrieved_array = np.frombuffer(retrieved_bytes, dtype=np.float64).reshape(1000, 1000)
            
            if np.array_equal(large_array, retrieved_array):
                print("   ✓ Array retrieved successfully!")
            
            # Clean up
            await pool.deallocate(array_block)
        
        # Clean up
        await pool.deallocate(block_id)
    
    # Show final stats
    print("\n📊 Final Memory Pool Stats:")
    stats = await pool.get_stats()
    for node_id, node_stats in stats['nodes'].items():
        print(f"   {node_id}: {node_stats['blocks_count']} blocks, {node_stats['total_mb']:.2f} MB")
    
    # Shutdown
    print("\n🛑 Shutting down memory pool...")
    await pool.shutdown()
    print("   ✓ Done!")


if __name__ == "__main__":
    asyncio.run(main())
