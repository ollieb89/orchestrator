"""Ray actor for persistent distributed memory storage."""

from __future__ import annotations

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


@ray.remote
class DistributedMemoryActor:
    """Ray actor for persistent distributed memory management."""
    
    def __init__(self):
        self._stored_objects: Dict[str, MemoryObject] = {}
        logger.info("Distributed memory actor initialized")
    
    def store(self, key: str, data: Any, preferred_node: Optional[str] = None) -> bool:
        """Store data in distributed memory."""
        try:
            # Create Ray object reference
            object_ref = ray.put(data)
            
            # Get size estimate (rough approximation)
            size_bytes = sys.getsizeof(data)
            
            # Store metadata
            self._stored_objects[key] = MemoryObject(
                object_id=key,
                object_ref=object_ref,
                size_bytes=size_bytes,
                created_at=datetime.now(UTC),
                node_hint=preferred_node
            )
            
            logger.info(
                "Stored object in distributed memory",
                key=key,
                size_bytes=size_bytes,
                preferred_node=preferred_node,
            )
            return True
            
        except Exception as e:
            logger.error(
                "Failed to store object in distributed memory",
                key=key,
                error=str(e),
            )
            return False
    
    def retrieve(self, key: str) -> Optional[Any]:
        """Retrieve data from distributed memory."""
        if key not in self._stored_objects:
            logger.warning("Object not found in distributed memory", key=key)
            return None
            
        try:
            memory_obj = self._stored_objects[key]
            data = ray.get(memory_obj.object_ref)
            logger.debug("Retrieved object from distributed memory", key=key)
            return data
            
        except Exception as e:
            logger.error(
                "Failed to retrieve object from distributed memory",
                key=key,
                error=str(e),
            )
            return None
    
    def delete(self, key: str) -> bool:
        """Delete object from distributed memory."""
        if key not in self._stored_objects:
            logger.warning("Object not found for deletion", key=key)
            return False
            
        try:
            del self._stored_objects[key]
            logger.info("Deleted object from distributed memory", key=key)
            return True
            
        except Exception as e:
            logger.error(
                "Failed to delete object from distributed memory",
                key=key,
                error=str(e),
            )
            return False
    
    def list_objects(self) -> List[Dict[str, Any]]:
        """List all stored objects."""
        objects = []
        for key, memory_obj in self._stored_objects.items():
            objects.append({
                "key": key,
                "size_mb": memory_obj.size_bytes / (1024 * 1024),
                "created_at": memory_obj.created_at.isoformat(),
                "node_hint": memory_obj.node_hint
            })
        return objects
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        total_objects = len(self._stored_objects)
        total_bytes = sum(obj.size_bytes for obj in self._stored_objects.values())
        
        return {
            "total_objects": total_objects,
            "total_mb": total_bytes / (1024 * 1024),
            "objects": self.list_objects()
        }
