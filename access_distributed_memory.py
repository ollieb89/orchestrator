#!/usr/bin/env python3
"""
Example script to access the 10GB distributed memory on gpu2 from gpu-master.
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

async def access_distributed_memory():
    """Access and use the allocated 10GB memory on gpu2."""
    
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
    
    print("🎯 Accessing your 10GB memory block on gpu2...")
    
    # Your allocated block from the previous command
    block_id = "block_0_gpu2"
    
    if block_id in memory_pool.blocks:
        block = memory_pool.blocks[block_id]
        print(f"✅ Found memory block: {block.block_id}")
        print(f"📍 Location: {block.node_id}")
        print(f"💾 Size: {block.size_bytes / (1024**3):.2f} GB")
        
        # Write some test data to the block
        test_data = b"Hello from gpu-master! This is stored in gpu2's memory!" * 100
        print(f"📝 Writing {len(test_data)} bytes to distributed memory...")
        
        success = await memory_pool.write(block_id, test_data)
        if success:
            print("✅ Data written successfully!")
            
            # Read it back
            print("📖 Reading data back from distributed memory...")
            retrieved_data = await memory_pool.read(block_id, len(test_data))
            
            if retrieved_data:
                print(f"✅ Retrieved {len(retrieved_data)} bytes!")
                print(f"📄 Sample data: {retrieved_data[:100]}...")
            else:
                print("❌ Failed to read data")
        else:
            print("❌ Failed to write data")
    else:
        print(f"❌ Block {block_id} not found")
        print("Available blocks:")
        for bid in memory_pool.blocks:
            block = memory_pool.blocks[bid]
            print(f"  - {bid}: {block.size_bytes / (1024**3):.2f} GB on {block.node_id}")

if __name__ == "__main__":
    asyncio.run(access_distributed_memory())
