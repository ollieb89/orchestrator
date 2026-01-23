#!/usr/bin/env python3
"""
Quick write to distributed memory - allocate and write in one step.
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

async def quick_write():
    """Quick write: allocate and write data to gpu2 memory."""
    
    # Load cluster config
    with open('config/my-cluster-enhanced.yaml', 'r') as f:
        config_data = yaml.safe_load(f)
    cluster_config = ClusterConfig(**config_data)
    
    # Initialize Ray
    if not ray.is_initialized():
        ray.init(address='192.168.1.100:6399')
    
    # Initialize distributed memory pool
    memory_pool = DistributedMemoryPool(cluster_config)
    await memory_pool.initialize(persistent=True)
    
    print("🎯 Quick write to gpu2 distributed memory...")
    
    # Allocate 10GB on gpu2
    size_gb = 10
    size_bytes = int(size_gb * 1024**3)
    
    print(f"📍 Allocating {size_gb}GB on gpu2...")
    block_id = await memory_pool.allocate(size_bytes, preferred_node="gpu2")
    
    if block_id:
        print(f"✅ Allocated block: {block_id}")
        
        # Write some sample data
        data = b"Hello from gpu-master! This is stored on gpu2! " * 10000
        data += b"DATA_BLOCK_MARKER_" + b"X" * (1024 * 1024)  # 1MB marker
        
        print(f"📝 Writing {len(data) / (1024**2):.2f} MB to distributed memory...")
        
        success = await memory_pool.write(block_id, data)
        
        if success:
            print("✅ Data written successfully!")
            print(f"📍 Block ID: {block_id}")
            print(f"💾 Size: {len(data) / (1024**2):.2f} MB")
            print(f"🔗 Location: gpu2 node")
            
            # Verify
            retrieved = await memory_pool.read(block_id, len(data))
            if retrieved == data:
                print("✅ Data verified!")
                print(f"📄 Sample: {retrieved[:100]}..." if len(retrieved) > 100 else f"📄 Data: {retrieved}")
            else:
                print("❌ Verification failed!")
                
        else:
            print("❌ Failed to write data")
            
    else:
        print("❌ Failed to allocate memory")

if __name__ == "__main__":
    asyncio.run(quick_write())
