"""Helper utilities for distributed memory operations."""

from __future__ import annotations

import asyncio
import pickle
from typing import Any, Optional
import numpy as np
import structlog

logger = structlog.get_logger(__name__)


class DistributedMemoryHelper:
    """Helper class for common distributed memory operations."""
    
    def __init__(self, memory_pool):
        """Initialize with a distributed memory pool instance."""
        self.pool = memory_pool
        
    async def store_object(
        self,
        obj: Any,
        preferred_node: Optional[str] = None,
    ) -> Optional[str]:
        """Store a Python object in distributed memory.
        
        Args:
            obj: Python object to store (will be pickled)
            preferred_node: Optional preferred node for storage
            
        Returns:
            Block ID if successful, None otherwise
        """
        try:
            # Serialize object
            data = pickle.dumps(obj)
            
            # Allocate memory
            block_id = await self.pool.allocate(len(data), preferred_node)
            if not block_id:
                return None
                
            # Write data
            success = await self.pool.write(block_id, data)
            if not success:
                await self.pool.deallocate(block_id)
                return None
                
            logger.info(
                "Stored object in distributed memory",
                block_id=block_id,
                size_mb=len(data) / (1024**2),
                node=preferred_node or "auto",
            )
            return block_id
            
        except Exception as e:
            logger.error("Failed to store object", error=str(e))
            return None
    
    async def retrieve_object(self, block_id: str) -> Optional[Any]:
        """Retrieve a Python object from distributed memory.
        
        Args:
            block_id: Block ID to retrieve
            
        Returns:
            Deserialized Python object if successful, None otherwise
        """
        try:
            # Get block info
            if block_id not in self.pool.blocks:
                logger.error("Block not found", block_id=block_id)
                return None
                
            block = self.pool.blocks[block_id]
            
            # Read data
            data = await self.pool.read(block_id, block.size_bytes)
            if not data:
                return None
                
            # Deserialize
            obj = pickle.loads(data)
            
            logger.info(
                "Retrieved object from distributed memory",
                block_id=block_id,
                size_mb=len(data) / (1024**2),
            )
            return obj
            
        except Exception as e:
            logger.error("Failed to retrieve object", block_id=block_id, error=str(e))
            return None
    
    async def store_numpy_array(
        self,
        array: np.ndarray,
        preferred_node: Optional[str] = None,
    ) -> Optional[str]:
        """Store a NumPy array in distributed memory.
        
        Args:
            array: NumPy array to store
            preferred_node: Optional preferred node for storage
            
        Returns:
            Block ID if successful, None otherwise
        """
        try:
            # Convert to bytes
            array_bytes = array.tobytes()
            
            # Store metadata separately (shape, dtype)
            metadata = {
                'shape': array.shape,
                'dtype': str(array.dtype),
            }
            metadata_bytes = pickle.dumps(metadata)
            
            # Allocate memory for data + metadata
            total_size = len(array_bytes) + len(metadata_bytes) + 8  # 8 bytes for metadata size
            block_id = await self.pool.allocate(total_size, preferred_node)
            if not block_id:
                return None
            
            # Write metadata size (8 bytes)
            metadata_size_bytes = len(metadata_bytes).to_bytes(8, byteorder='little')
            await self.pool.write(block_id, metadata_size_bytes, offset=0)
            
            # Write metadata
            await self.pool.write(block_id, metadata_bytes, offset=8)
            
            # Write array data
            success = await self.pool.write(block_id, array_bytes, offset=8 + len(metadata_bytes))
            if not success:
                await self.pool.deallocate(block_id)
                return None
            
            logger.info(
                "Stored numpy array in distributed memory",
                block_id=block_id,
                shape=array.shape,
                dtype=array.dtype,
                size_mb=len(array_bytes) / (1024**2),
            )
            return block_id
            
        except Exception as e:
            logger.error("Failed to store numpy array", error=str(e))
            return None
    
    async def retrieve_numpy_array(self, block_id: str) -> Optional[np.ndarray]:
        """Retrieve a NumPy array from distributed memory.
        
        Args:
            block_id: Block ID to retrieve
            
        Returns:
            NumPy array if successful, None otherwise
        """
        try:
            # Read metadata size
            metadata_size_bytes = await self.pool.read(block_id, 8, offset=0)
            if not metadata_size_bytes:
                return None
            
            metadata_size = int.from_bytes(metadata_size_bytes, byteorder='little')
            
            # Read metadata
            metadata_bytes = await self.pool.read(block_id, metadata_size, offset=8)
            if not metadata_bytes:
                return None
            
            metadata = pickle.loads(metadata_bytes)
            
            # Calculate array data size
            block = self.pool.blocks[block_id]
            array_size = block.size_bytes - 8 - metadata_size
            
            # Read array data
            array_bytes = await self.pool.read(block_id, array_size, offset=8 + metadata_size)
            if not array_bytes:
                return None
            
            # Reconstruct array
            array = np.frombuffer(array_bytes, dtype=metadata['dtype']).reshape(metadata['shape'])
            
            logger.info(
                "Retrieved numpy array from distributed memory",
                block_id=block_id,
                shape=metadata['shape'],
                dtype=metadata['dtype'],
            )
            return array
            
        except Exception as e:
            logger.error("Failed to retrieve numpy array", block_id=block_id, error=str(e))
            return None
    
    async def cache_large_data(
        self,
        key: str,
        data: Any,
        preferred_node: Optional[str] = None,
    ) -> bool:
        """Cache large data with a string key.
        
        Args:
            key: Cache key
            data: Data to cache
            preferred_node: Optional preferred node
            
        Returns:
            True if successful, False otherwise
        """
        # Store in pool with key as block_id prefix
        block_id = f"cache_{key}"
        
        # Check if already exists
        if block_id in self.pool.blocks:
            await self.pool.deallocate(block_id)
        
        # Store new data
        result = await self.store_object(data, preferred_node)
        return result is not None
    
    async def get_cached_data(self, key: str) -> Optional[Any]:
        """Retrieve cached data by key.
        
        Args:
            key: Cache key
            
        Returns:
            Cached data if found, None otherwise
        """
        block_id = f"cache_{key}"
        if block_id not in self.pool.blocks:
            return None
        
        return await self.retrieve_object(block_id)
    
    async def clear_cache(self, key: str) -> bool:
        """Clear cached data by key.
        
        Args:
            key: Cache key
            
        Returns:
            True if successful, False otherwise
        """
        block_id = f"cache_{key}"
        if block_id not in self.pool.blocks:
            return False
        
        return await self.pool.deallocate(block_id)
    
    async def get_memory_usage_summary(self) -> dict:
        """Get a summary of memory usage across nodes.
        
        Returns:
            Dictionary with usage statistics
        """
        stats = await self.pool.get_stats()
        
        summary = {
            'total_blocks': stats['total_blocks'],
            'total_memory_mb': 0,
            'nodes': {},
        }
        
        for node_id, node_stats in stats['nodes'].items():
            summary['nodes'][node_id] = {
                'blocks': node_stats['blocks_count'],
                'memory_mb': node_stats['total_mb'],
            }
            summary['total_memory_mb'] += node_stats['total_mb']
        
        return summary


async def create_distributed_cache(
    cluster_config,
    cache_size_gb: float = 10.0,
    preferred_node: Optional[str] = None,
) -> Optional[str]:
    """Create a distributed cache pool.
    
    Args:
        cluster_config: Cluster configuration
        cache_size_gb: Size of cache in GB
        preferred_node: Optional preferred node
        
    Returns:
        Cache block ID if successful, None otherwise
    """
    from distributed_grid.orchestration.distributed_memory_pool import DistributedMemoryPool
    
    pool = DistributedMemoryPool(cluster_config)
    await pool.initialize()
    
    cache_size_bytes = int(cache_size_gb * 1024**3)
    block_id = await pool.allocate(cache_size_bytes, preferred_node)
    
    if block_id:
        logger.info(
            "Created distributed cache",
            block_id=block_id,
            size_gb=cache_size_gb,
            node=preferred_node or "auto",
        )
    
    return block_id
