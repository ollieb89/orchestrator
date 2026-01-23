"""Distributed memory manager using Ray object store for cluster-wide data access."""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional

import ray
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
    """Manages distributed memory using Ray's object store with a registry actor."""
    
    def __init__(self, cluster_config):
        self.cluster_config = cluster_config
        self._registry_actor: Optional[ray.ObjectRef] = None
        self._initialized = False
        
    async def initialize(self) -> None:
        """Initialize the memory manager."""
        if self._initialized:
            return
            
        # Ensure Ray is connected with fixed namespace
        if not ray.is_initialized():
            ray.init(address="auto", namespace="distributed_memory")
        
        # Create or get the registry actor
        try:
            self._registry_actor = ray.get_actor("distributed_memory_registry", namespace="distributed_memory")
        except ValueError:
            # Create the registry actor that stores actual data
            @ray.remote
            class MemoryRegistry:
                def __init__(self):
                    self._objects: Dict[str, Any] = {}
                
                def store_data(self, key: str, data: Any, metadata: Dict[str, Any]) -> bool:
                    # Store the actual data (not ObjectRef)
                    self._objects[key] = {
                        "data": data,
                        "metadata": metadata
                    }
                    return True
                
                def get_data(self, key: str) -> Optional[Any]:
                    if key in self._objects:
                        return self._objects[key]["data"]
                    return None
                
                def list_all(self) -> List[Dict[str, Any]]:
                    return [obj["metadata"] for obj in self._objects.values()]
                
                def delete(self, key: str) -> bool:
                    if key in self._objects:
                        del self._objects[key]
                        return True
                    return False
                
                def get_stats(self) -> Dict[str, Any]:
                    objects = list(self._objects.values())
                    total_bytes = sum(obj["metadata"]["size_bytes"] for obj in objects)
                    return {
                        "total_objects": len(objects),
                        "total_mb": total_bytes / (1024 * 1024),
                        "objects": [obj["metadata"] for obj in objects]
                    }
            
            self._registry_actor = MemoryRegistry.options(
                name="distributed_memory_registry",
                namespace="distributed_memory",
                lifetime="detached"
            ).remote()
            
        self._initialized = True
        logger.info("Distributed memory manager initialized")
        
    async def store(self, key: str, data: Any, preferred_node: Optional[str] = None) -> bool:
        """Store data in distributed memory."""
        if not self._initialized:
            await self.initialize()
            
        try:
            # Create metadata
            metadata = {
                "key": key,
                "size_bytes": sys.getsizeof(data),
                "created_at": datetime.now(UTC).isoformat(),
                "node_hint": preferred_node
            }
            
            # Store data directly with the registry actor
            result_ref = self._registry_actor.register.remote(key, data, metadata)
            success = ray.get(result_ref)
            
            if success:
                logger.info(
                    "Stored object in distributed memory",
                    key=key,
                    size_bytes=metadata["size_bytes"],
                    preferred_node=preferred_node,
                )
            return success
            
        except Exception as e:
            logger.error(
                "Failed to store object in distributed memory",
                key=key,
                error=str(e),
            )
            return False
            
    async def retrieve(self, key: str) -> Optional[Any]:
        """Retrieve data from distributed memory."""
        if not self._initialized:
            await self.initialize()
            
        try:
            # Get data directly from registry actor
            result_ref = self._registry_actor.get.remote(key)
            data = ray.get(result_ref)
            
            if data is not None:
                logger.debug("Retrieved object from distributed memory", key=key)
                return data
            else:
                logger.warning("Object not found in distributed memory", key=key)
                return None
            
        except Exception as e:
            logger.error(
                "Failed to retrieve object from distributed memory",
                key=key,
                error=str(e),
            )
            return None
    
    async def delete(self, key: str) -> bool:
        """Delete object from distributed memory."""
        if not self._initialized:
            await self.initialize()
            
        try:
            result_ref = self._registry_actor.delete.remote(key)
            success = ray.get(result_ref)
            
            if success:
                logger.info("Deleted object from distributed memory", key=key)
            else:
                logger.warning("Object not found for deletion", key=key)
            return success
            
        except Exception as e:
            logger.error(
                "Failed to delete object from distributed memory",
                key=key,
                error=str(e),
            )
            return False
    
    async def list_objects(self) -> List[Dict[str, Any]]:
        """List all stored objects."""
        if not self._initialized:
            await self.initialize()
            
        try:
            result_ref = self._registry_actor.list_all.remote()
            objects = ray.get(result_ref)
            return objects
            
        except Exception as e:
            logger.error(
                "Failed to list objects in distributed memory",
                error=str(e),
            )
            return []
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        if not self._initialized:
            await self.initialize()
            
        try:
            result_ref = self._registry_actor.get_stats.remote()
            stats = ray.get(result_ref)
            return stats
            
        except Exception as e:
            logger.error(
                "Failed to get memory statistics",
                error=str(e),
            )
            return {
                "total_objects": 0,
                "total_mb": 0.0,
                "objects": []
            }
