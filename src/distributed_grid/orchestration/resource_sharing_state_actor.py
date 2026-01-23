"""Ray actor for persistent resource sharing state management."""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, UTC, timedelta

import ray

from distributed_grid.orchestration.resource_sharing_types import (
    ResourceRequest,
    ResourceAllocation,
    ResourceType,
    AllocationPriority,
)

logger = logging.getLogger(__name__)


@ray.remote
class ResourceSharingStateActor:
    """Ray actor for managing persistent resource sharing state."""
    
    def __init__(self):
        """Initialize the actor with empty state."""
        self._resource_requests: List[ResourceRequest] = []
        self._active_allocations: List[ResourceAllocation] = []
        self._shared_resources: Dict[str, Dict[ResourceType, float]] = {}
        self._allocation_counter = 0
        
    def add_request(self, request: ResourceRequest) -> None:
        """Add a resource request."""
        self._resource_requests.append(request)
        logger.info(f"Added request to persistent state: {request.request_id}")
        
    def remove_request(self, request_id: str) -> bool:
        """Remove a resource request."""
        for i, req in enumerate(self._resource_requests):
            if req.request_id == request_id:
                del self._resource_requests[i]
                logger.info(f"Removed request from persistent state: {request_id}")
                return True
        return False
        
    def add_allocation(self, allocation: ResourceAllocation) -> None:
        """Add a resource allocation."""
        self._active_allocations.append(allocation)
        logger.info(f"Added allocation to persistent state: {allocation.allocation_id}")
        
    def remove_allocation(self, allocation_id: str) -> bool:
        """Remove a resource allocation."""
        for i, alloc in enumerate(self._active_allocations):
            if alloc.allocation_id == allocation_id:
                del self._active_allocations[i]
                logger.info(f"Removed allocation from persistent state: {allocation_id}")
                return True
        return False
        
    def get_requests(self) -> List[ResourceRequest]:
        """Get all resource requests."""
        return self._resource_requests.copy()
        
    def get_allocations(self) -> List[ResourceAllocation]:
        """Get all active allocations."""
        return self._active_allocations.copy()
        
    def set_shared_resources(self, node_id: str, resources: Dict[ResourceType, float]) -> None:
        """Set shared resources for a node."""
        self._shared_resources[node_id] = resources.copy()
        
    def get_shared_resources(self) -> Dict[str, Dict[ResourceType, float]]:
        """Get all shared resources."""
        return {k: v.copy() for k, v in self._shared_resources.items()}
        
    def cleanup_expired(self) -> Dict[str, int]:
        """Clean up expired requests and allocations."""
        now = datetime.now(UTC)
        
        # Clean expired requests
        initial_requests = len(self._resource_requests)
        self._resource_requests = [
            req for req in self._resource_requests 
            if not req.is_expired
        ]
        expired_requests = initial_requests - len(self._resource_requests)
        
        # Clean expired allocations
        initial_allocations = len(self._active_allocations)
        self._active_allocations = [
            alloc for alloc in self._active_allocations 
            if not alloc.is_expired
        ]
        expired_allocations = initial_allocations - len(self._active_allocations)
        
        return {
            "expired_requests": expired_requests,
            "expired_allocations": expired_allocations,
        }
        
    def get_status(self) -> Dict[str, Any]:
        """Get current status."""
        return {
            "pending_requests_count": len(self._resource_requests),
            "active_allocations_count": len(self._active_allocations),
            "shared_resources": {
                node: {str(k): v for k, v in resources.items()}
                for node, resources in self._shared_resources.items()
            },
            "allocations": [
                {
                    "allocation_id": alloc.allocation_id,
                    "request_id": alloc.request_id,
                    "source_node": alloc.source_node,
                    "target_node": alloc.target_node,
                    "resource_type": str(alloc.resource_type),
                    "amount": alloc.amount,
                    "allocated_at": alloc.allocated_at.isoformat(),
                    "expires_at": (
                        (alloc.allocated_at + alloc.lease_duration).isoformat()
                        if alloc.lease_duration else "never"
                    ),
                }
                for alloc in self._active_allocations
            ],
        }


# Global actor handle
_state_actor: Optional[ray.actor.ActorHandle] = None


def get_state_actor() -> ray.actor.ActorHandle:
    """Get or create the persistent state actor."""
    global _state_actor
    
    if _state_actor is None:
        # Try to get existing actor
        try:
            _state_actor = ray.get_actor("ResourceSharingStateActor")
        except ValueError:
            # Actor doesn't exist, create a new detached one
            _state_actor = ResourceSharingStateActor.options(
                lifetime="detached",
                name="ResourceSharingStateActor",
                max_concurrency=100,
            ).remote()
            logger.info("Created new persistent state actor")
            
    return _state_actor


async def ensure_actor_initialized() -> None:
    """Ensure the state actor is initialized and ready."""
    actor = get_state_actor()
    # Ping the actor to ensure it's ready
    try:
        await actor.cleanup_expired.remote()
    except Exception as e:
        logger.error(f"Failed to initialize state actor: {e}")
        # Try to kill and recreate the actor
        try:
            ray.kill(actor)
        except:
            pass
        # Recreate
        global _state_actor
        _state_actor = None
        actor = get_state_actor()
