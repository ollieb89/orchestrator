#!/usr/bin/env python3
"""
Write data to the distributed memory block on gpu2.
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

async def write_to_memory():
    """Write custom data to the distributed memory block."""
    
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
    
    print("🎯 Writing to distributed memory on gpu2...")
    
    # Your allocated block
    block_id = "block_0_gpu2"
    
    if block_id in memory_pool.blocks:
        block = memory_pool.blocks[block_id]
        print(f"📍 Using block: {block.block_id}")
        print(f"💾 Available size: {block.size_bytes / (1024**3):.2f} GB")
        
        # Get user input or use default data
        print("\n📝 What would you like to write to memory?")
        print("1. Custom text message")
        print("2. Binary data pattern")
        print("3. Large data chunk (1MB)")
        print("4. File content")
        
        choice = input("\nEnter choice (1-4): ").strip()
        
        if choice == "1":
            message = input("Enter your message: ")
            data = message.encode('utf-8')
            print(f"📄 Writing message: {message}")
            
        elif choice == "2":
            pattern = input("Enter pattern (e.g., 'ABC', '123'): ")
            repeats = int(input("How many repeats? "))
            data = pattern.encode('utf-8') * repeats
            print(f"🔄 Writing pattern '{pattern}' repeated {repeats} times")
            
        elif choice == "3":
            size_mb = int(input("Size in MB (max 10240): "))
            size_bytes = size_mb * 1024 * 1024
            data = b'X' * size_bytes
            print(f"📦 Writing {size_mb}MB of data")
            
        elif choice == "4":
            file_path = input("Enter file path: ")
            try:
                with open(file_path, 'rb') as f:
                    data = f.read()
                print(f"📁 Reading file: {file_path}")
            except FileNotFoundError:
                print("❌ File not found!")
                return
        
        else:
            print("❌ Invalid choice")
            return
        
        # Write data to distributed memory
        print(f"💾 Writing {len(data) / (1024**2):.2f} MB to gpu2...")
        
        success = await memory_pool.write(block_id, data)
        
        if success:
            print("✅ Data written successfully!")
            print(f"📍 Location: gpu2 node")
            print(f"🔑 Block ID: {block_id}")
            print(f"📊 Size: {len(data) / (1024**2):.2f} MB")
            
            # Verify by reading back
            print("\n🔍 Verifying data...")
            retrieved = await memory_pool.read(block_id, len(data))
            
            if retrieved == data:
                print("✅ Data integrity verified!")
            else:
                print("❌ Data integrity check failed!")
                
        else:
            print("❌ Failed to write data")
            
    else:
        print(f"❌ Block {block_id} not found")
        print("Available blocks:")
        for bid in memory_pool.blocks:
            block = memory_pool.blocks[bid]
            print(f"  - {bid}: {block.size_bytes / (1024**3):.2f} GB on {block.node_id}")

if __name__ == "__main__":
    asyncio.run(write_to_memory())
