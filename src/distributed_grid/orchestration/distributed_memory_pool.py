"""Distributed memory pool for transparent remote memory usage."""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional, Any
from dataclasses import dataclass
import pickle

import ray
import structlog
from distributed_grid.utils.node_utils import get_host_to_ray_node_mapping

logger = structlog.get_logger(__name__)


@dataclass
class MemoryBlock:
    """Represents a block of distributed memory."""
    block_id: str
    size_bytes: int
    node_id: str
    object_ref: Optional[ray.ObjectRef] = None


@ray.remote
class DistributedMemoryStore:
    """Ray actor that stores memory blocks on a specific node."""
    
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.blocks: Dict[str, bytes] = {}
        
    def allocate(self, block_id: str, size_bytes: int) -> bool:
        """Allocate a memory block."""
        try:
            self.blocks[block_id] = bytearray(size_bytes)
            return True
        except MemoryError:
            return False
            
    def write(self, block_id: str, data: bytes, offset: int = 0) -> bool:
        """Write data to a memory block."""
        if block_id not in self.blocks:
            return False
        try:
            self.blocks[block_id][offset:offset+len(data)] = data
            return True
        except Exception:
            return False
            
    def read(self, block_id: str, size: int, offset: int = 0) -> Optional[bytes]:
        """Read data from a memory block."""
        if block_id not in self.blocks:
            return None
        return bytes(self.blocks[block_id][offset:offset+size])
        
    def deallocate(self, block_id: str) -> bool:
        """Deallocate a memory block."""
        if block_id in self.blocks:
            del self.blocks[block_id]
            return True
        return False
        
    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        total_bytes = sum(len(block) for block in self.blocks.values())
        return {
            "node_id": self.node_id,
            "blocks_count": len(self.blocks),
            "total_bytes": total_bytes,
            "total_mb": total_bytes / (1024**2),
        }


class DistributedMemoryPool:
    """Manages distributed memory across cluster nodes."""
    
    def __init__(self, cluster_config):
        self.cluster_config = cluster_config
        self.memory_stores: Dict[str, ray.ActorHandle] = {}
        self.blocks: Dict[str, MemoryBlock] = {}
        self._initialized = False
        
    async def initialize(self) -> None:
        """Initialize memory stores on all nodes."""
        if self._initialized:
            return
            
        logger.info("Initializing distributed memory pool")
        
        # Get Ray node mapping
        host_to_ray_id = get_host_to_ray_node_mapping()
        logger.debug("Current Ray node mapping", mapping=host_to_ray_id)
        
        # Create memory store actors on each node
        for node in self.cluster_config.nodes:
            if node.role == "worker":
                # Find the actual Ray node ID for this host
                # Use resolve_hostname_to_ip to normalize node.host
                from distributed_grid.utils.node_utils import resolve_hostname_to_ip
                
                host_ip = resolve_hostname_to_ip(node.host)
                logger.debug("Resolving host", host=node.host, resolved_ip=host_ip)
                
                ray_node_id = host_to_ray_id.get(host_ip) if host_ip else None
                
                # Fallback to direct match if IP resolution failed or didn't match
                if not ray_node_id:
                    ray_node_id = host_to_ray_id.get(node.host)
                
                if not ray_node_id:
                    logger.warning("Ray node not found for host", 
                                 host=node.host, 
                                 resolved_ip=host_ip,
                                 available_ips=list(host_to_ray_id.keys()))
                    continue
                
                # Create actor pinned to specific node using actual Ray node ID
                store = DistributedMemoryStore.options(
                    name=f"memory_store_{node.name}",
                    max_concurrency=10,
                    # Pin to node using actual Ray node ID
                    resources={f"node:{ray_node_id}": 0.01}
                ).remote(node.name)
                
                self.memory_stores[node.name] = store
                logger.info("Created memory store", node_name=node.name, ray_node_id=ray_node_id)
                
        self._initialized = True
        logger.info("Distributed memory pool initialized", 
                   stores_count=len(self.memory_stores))
        
    async def allocate(self, size_bytes: int, preferred_node: Optional[str] = None) -> Optional[str]:
        """Allocate distributed memory block."""
        if not self._initialized:
            await self.initialize()
            
        # Select node (prefer specified node, otherwise pick one with space)
        target_node = preferred_node
        if not target_node or target_node not in self.memory_stores:
            # Pick first available worker
            target_node = next(iter(self.memory_stores.keys()), None)
            
        if not target_node:
            logger.error("No available nodes for memory allocation")
            return None
            
        # Generate block ID
        block_id = f"block_{len(self.blocks)}_{target_node}"
        
        # Allocate on remote node
        store = self.memory_stores[target_node]
        success = await store.allocate.remote(block_id, size_bytes)
        
        if not success:
            logger.error("Failed to allocate memory block", 
                        block_id=block_id, node=target_node)
            return None
            
        # Track block
        self.blocks[block_id] = MemoryBlock(
            block_id=block_id,
            size_bytes=size_bytes,
            node_id=target_node,
        )
        
        logger.info("Allocated memory block", 
                   block_id=block_id, 
                   size_mb=size_bytes/(1024**2),
                   node=target_node)
        return block_id
        
    async def write(self, block_id: str, data: bytes, offset: int = 0) -> bool:
        """Write data to distributed memory."""
        if block_id not in self.blocks:
            return False
            
        block = self.blocks[block_id]
        store = self.memory_stores[block.node_id]
        return await store.write.remote(block_id, data, offset)
        
    async def read(self, block_id: str, size: int, offset: int = 0) -> Optional[bytes]:
        """Read data from distributed memory."""
        if block_id not in self.blocks:
            return None
            
        block = self.blocks[block_id]
        store = self.memory_stores[block.node_id]
        return await store.read.remote(block_id, size, offset)
        
    async def deallocate(self, block_id: str) -> bool:
        """Deallocate distributed memory block."""
        if block_id not in self.blocks:
            return False
            
        block = self.blocks[block_id]
        store = self.memory_stores[block.node_id]
        success = await store.deallocate.remote(block_id)
        
        if success:
            del self.blocks[block_id]
            logger.info("Deallocated memory block", block_id=block_id)
            
        return success
        
    async def get_stats(self) -> Dict[str, Any]:
        """Get memory pool statistics."""
        stats = {
            "total_blocks": len(self.blocks),
            "nodes": {}
        }
        
        for node_id, store in self.memory_stores.items():
            node_stats = await store.get_stats.remote()
            stats["nodes"][node_id] = node_stats
            
        return stats
        
    async def shutdown(self) -> None:
        """Shutdown the memory pool."""
        logger.info("Shutting down distributed memory pool")
        
        # Deallocate all blocks
        for block_id in list(self.blocks.keys()):
            await self.deallocate(block_id)
            
        # Kill actors
        for store in self.memory_stores.values():
            ray.kill(store)
            
        self.memory_stores.clear()
        self._initialized = False
