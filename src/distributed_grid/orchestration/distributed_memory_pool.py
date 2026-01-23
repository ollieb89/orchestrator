"""Distributed memory pool for transparent remote memory usage."""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional, Any
from dataclasses import dataclass
import pickle

import ray
import logging
from typing import Dict, Optional, Any
from dataclasses import dataclass
import pickle
import time
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
        # Use standard logging inside the actor to avoid serialization issues
        self._logger = logging.getLogger(f"MemoryStore.{node_id}")
        
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
            "status": "alive"
        }


class DistributedMemoryPool:
    """Manages distributed memory across cluster nodes."""
    
    # Explicit namespace for detached actors
    ACTOR_NAMESPACE = "distributed_memory_pool"
    
    def __init__(self, cluster_config):
        self.cluster_config = cluster_config
        self.memory_stores: Dict[str, ray.ActorHandle] = {}
        self.blocks: Dict[str, MemoryBlock] = {}
        self._initialized = False
        
    async def initialize(self, persistent: bool = False) -> None:
        """Initialize memory stores on all nodes."""
        if self._initialized:
            return
            
        logger.info("Initializing distributed memory pool", persistent=persistent)
        
        # Load persisted stores if requested
        persisted_stores = []
        if persistent:
            from distributed_grid.orchestration.resource_sharing_persistence import ResourceSharingPersistence
            persistence = ResourceSharingPersistence()
            persisted_stores = persistence.load_memory_stores()
            logger.debug("Loaded persisted memory stores", count=len(persisted_stores))
        
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
                
                # Check if actor already exists (persistent mode)
                actor_name = f"memory_store_{node.name}"
                store = None
                try:
                    # Try to get existing actor with explicit namespace
                    store = ray.get_actor(actor_name, namespace=self.ACTOR_NAMESPACE)
                    logger.info("Connected to existing memory store", node_name=node.name)
                except ValueError:
                    # Create new actor if not exists
                    store = DistributedMemoryStore.options(
                        name=actor_name,
                        namespace=self.ACTOR_NAMESPACE,
                        max_concurrency=10,
                        lifetime="detached" if persistent else None,
                        # Pin to node using actual Ray node ID
                        resources={f"node:{ray_node_id}": 0.01}
                    ).remote(node.name)
                    logger.info("Created new memory store", node_name=node.name, ray_node_id=ray_node_id, persistent=persistent)
                
                self.memory_stores[node.name] = store
                
        # Update persistence if in persistent mode
        if persistent:
            from distributed_grid.orchestration.resource_sharing_persistence import ResourceSharingPersistence
            persistence = ResourceSharingPersistence()
            stores_data = []
            for node_name in self.memory_stores:
                stores_data.append({
                    "node_name": node_name,
                    "actor_name": f"memory_store_{node_name}"
                })
            persistence.save_memory_stores(stores_data)
                
        self._initialized = True
        logger.info("Distributed memory pool initialized", 
                   stores_count=len(self.memory_stores))
        
    async def _get_store(self, node_name: str) -> Optional[ray.ActorHandle]:
        """Get or recreate a memory store actor for a node."""
        actor_name = f"memory_store_{node_name}"
        
        # Check if we have it cached and it's alive
        if node_name in self.memory_stores:
            store = self.memory_stores[node_name]
            try:
                # Ping the actor to check if it's alive
                await store.get_stats.remote()
                return store
            except Exception:
                logger.warning("Memory store actor died, attempting to recreate", node_name=node_name)
                del self.memory_stores[node_name]

        # Try to get from Ray (persistent/detached mode)
        try:
            store = ray.get_actor(actor_name, namespace=self.ACTOR_NAMESPACE)
            self.memory_stores[node_name] = store
            return store
        except ValueError:
            # Not found, need to create
            pass
        except Exception as e:
            logger.error("Error getting actor from Ray", actor_name=actor_name, error=str(e))

        # Create new actor
        try:
            # Find the actual Ray node ID for this host
            from distributed_grid.utils.node_utils import get_host_to_ray_node_mapping, resolve_hostname_to_ip
            
            host_to_ray_id = get_host_to_ray_node_mapping()
            node_config = next((n for n in self.cluster_config.nodes if n.name == node_name), None)
            if not node_config:
                return None

            host_ip = resolve_hostname_to_ip(node_config.host)
            ray_node_id = host_to_ray_id.get(host_ip) or host_to_ray_id.get(node_config.host)
            
            if not ray_node_id:
                logger.warning("Ray node not found for host during recreation", node_name=node_name)
                return None

            store = DistributedMemoryStore.options(
                name=actor_name,
                namespace=self.ACTOR_NAMESPACE,
                max_concurrency=10,
                lifetime="detached",
                resources={f"node:{ray_node_id}": 0.01}
            ).remote(node_name)
            
            self.memory_stores[node_name] = store
            logger.info("Recreated memory store", node_name=node_name, ray_node_id=ray_node_id)
            return store
        except Exception as e:
            logger.error("Failed to create memory store actor", node_name=node_name, error=str(e))
            return None

    async def allocate(self, size_bytes: int, preferred_node: Optional[str] = None) -> Optional[str]:
        """Allocate distributed memory block."""
        if not self._initialized:
            await self.initialize()
            
        # Select nodes to try (prefer specified node, then others)
        nodes_to_try = []
        if preferred_node:
            nodes_to_try.append(preferred_node)
        
        # Add all other worker nodes
        other_nodes = [n.name for n in self.cluster_config.nodes if n.role == "worker" and n.name != preferred_node]
        nodes_to_try.extend(other_nodes)

        for target_node in nodes_to_try:
            store = await self._get_store(target_node)
            if not store:
                continue

            # Generate block ID
            block_id = f"block_{int(time.time())}_{len(self.blocks)}_{target_node}"
            
            try:
                # Allocate on remote node
                success = await store.allocate.remote(block_id, size_bytes)
                if success:
                    # Track block
                    self.blocks[block_id] = MemoryBlock(
                        block_id=block_id,
                        size_bytes=size_bytes,
                        node_id=target_node,
                    )
                    logger.info("Allocated memory block", block_id=block_id, size_mb=size_bytes/(1024**2), node=target_node)
                    return block_id
            except Exception as e:
                logger.warning("Failed to allocate on node, trying next", node=target_node, error=str(e))
                continue

        logger.error("Failed to allocate memory block on any available node")
        return None
        
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
        
    async def spill_object(self, object_ref: ray.ObjectRef, preferred_node: Optional[str] = None) -> Optional[str]:
        """Spill a Ray object to the distributed memory pool.
        
        Args:
            object_ref: The Ray ObjectRef to spill
            preferred_node: Optional preferred node for storage
            
        Returns:
            Block ID if successful, None otherwise
        """
        try:
            # Get data from Ray object store
            data = await object_ref
            serialized_data = pickle.dumps(data)
            size_bytes = len(serialized_data)
            
            # Allocate space in pool
            block_id = await self.allocate(size_bytes, preferred_node)
            if not block_id:
                return None
                
            # Write data to remote store
            success = await self.write(block_id, serialized_data)
            if not success:
                await self.deallocate(block_id)
                return None
                
            logger.info("Spilled object to distributed memory", 
                       block_id=block_id, size_mb=size_bytes/(1024**2))
            return block_id
        except Exception as e:
            logger.error("Failed to spill object", error=str(e))
            return None

    async def restore_object(self, block_id: str) -> Optional[ray.ObjectRef]:
        """Restore a spilled object back to Ray.
        
        Args:
            block_id: The ID of the block to restore
            
        Returns:
            New Ray ObjectRef if successful, None otherwise
        """
        try:
            if block_id not in self.blocks:
                return None
                
            block = self.blocks[block_id]
            serialized_data = await self.read(block_id, block.size_bytes)
            if not serialized_data:
                return None
                
            data = pickle.loads(serialized_data)
            new_ref = ray.put(data)
            
            # Deallocate from pool after restoration
            await self.deallocate(block_id)
            
            logger.info("Restored object from distributed memory", block_id=block_id)
            return new_ref
        except Exception as e:
            logger.error("Failed to restore object", block_id=block_id, error=str(e))
            return None

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
