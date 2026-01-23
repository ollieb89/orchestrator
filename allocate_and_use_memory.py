#!/usr/bin/env python3
"""
Complete example: Allocate and use distributed memory from gpu-master.
"""

import asyncio
import ray
import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from distributed_grid.orchestration.distributed_memory_pool import DistributedMemoryPool
from distributed_grid.config.models import ClusterConfig
import yaml

async def allocate_and_use_memory():
    """Allocate 10GB on gpu2 and use it from gpu-master."""
    
    # Load cluster config
    with open('config/my-cluster-enhanced.yaml', 'r') as f:
        config_data = yaml.safe_load(f)
    cluster_config = ClusterConfig(**config_data)
    
    # Initialize Ray (connect to existing cluster)
    if not ray.is_initialized():
        ray.init(address='192.168.1.100:6399')
    
    # Initialize distributed memory pool
    memory_pool = DistributedMemoryPool(cluster_config)
    await memory_pool.initialize(persistent=True)
    
    print("🎯 Allocating 10GB memory on gpu2 from gpu-master...")
    
    # Allocate 10GB on gpu2
    size_gb = 10
    size_bytes = int(size_gb * 1024**3)
    
    block_id = await memory_pool.allocate(size_bytes, preferred_node="gpu2")
    
    if block_id:
        print(f"✅ Successfully allocated {size_gb}GB on gpu2!")
        print(f"📍 Block ID: {block_id}")
        
        # Create some test data
        print("📊 Creating test data...")
        test_data = b"Hello from gpu-master! This data is stored on gpu2!" * 100000
        test_data += b"0" * (1024 * 1024)  # Add 1MB of zeros
        
        print(f"📝 Writing {len(test_data) / (1024**2):.2f} MB to distributed memory...")
        
        # Write data to the remote memory
        success = await memory_pool.write(block_id, test_data)
        if success:
            print("✅ Data written successfully to gpu2's memory!")
            
            # Read it back
            print("📖 Reading data back from gpu2...")
            retrieved_data = await memory_pool.read(block_id, len(test_data))
            
            if retrieved_data:
                print(f"✅ Retrieved {len(retrieved_data) / (1024**2):.2f} MB!")
                
                # Verify data integrity
                if test_data == retrieved_data:
                    print("✅ Data integrity verified!")
                    print(f"📄 Sample data: {retrieved_data[:100]}...")
                else:
                    print("❌ Data integrity check failed!")
            else:
                print("❌ Failed to read data")
        else:
            print("❌ Failed to write data")
            
        # Show memory usage
        print("\n📊 Current Memory Usage:")
        stats = await memory_pool.get_stats()
        for node_id, node_stats in stats.get("nodes", {}).items():
            print(f"  {node_id}: {node_stats.get('total_mb', 0):.2f} MB used")
            
        print(f"\n💡 You now have {size_gb}GB of memory on gpu2 accessible from gpu-master!")
        print(f"🔑 Use block_id '{block_id}' to access this memory in your applications.")
        
    else:
        print("❌ Failed to allocate memory")

if __name__ == "__main__":
    asyncio.run(allocate_and_use_memory())
