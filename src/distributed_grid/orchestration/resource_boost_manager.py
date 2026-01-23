"""Resource Boost Manager for dynamically borrowing resources from worker nodes.

This module allows the master node to temporarily borrow CPU, GPU, and RAM resources
from worker nodes, effectively boosting its capabilities for demanding tasks.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, UTC, timedelta
from typing import Dict, List, Optional, Any, Set
from enum import Enum

import ray
import structlog

from distributed_grid.monitoring.resource_metrics import (
    ResourceMetricsCollector,
    ResourceType,
)
from distributed_grid.config import ClusterConfig
from distributed_grid.orchestration.resource_sharing_manager import (
    ResourceSharingManager,
)
from distributed_grid.orchestration.resource_sharing_types import (
    AllocationPriority,
)
from distributed_grid.orchestration.resource_boost_persistence import (
    ResourceBoostPersistence,
)

logger = structlog.get_logger(__name__)


@dataclass
class ResourceBoost:
    """Represents a resource boost allocation."""
    boost_id: str
    source_node: str
    target_node: str
    resource_type: ResourceType
    amount: float
    allocated_at: datetime
    expires_at: Optional[datetime] = None
    ray_placement_group: Optional[str] = None
    is_active: bool = True


@dataclass
class ResourceBoostRequest:
    """A request to boost resources on a target node."""
    target_node: str
    resource_type: ResourceType
    amount: float
    priority: AllocationPriority = AllocationPriority.NORMAL
    duration_seconds: Optional[float] = None
    preferred_source: Optional[str] = None


class ResourceBoostManager:
    """Manages resource boosts from worker nodes to the master node."""
    
    def __init__(
        self,
        cluster_config: ClusterConfig,
        metrics_collector: ResourceMetricsCollector,
        resource_sharing_manager: ResourceSharingManager,
        default_boost_duration: timedelta = timedelta(hours=1),
        persistence: Optional[ResourceBoostPersistence] = None,
    ):
        """Initialize the resource boost manager.
        
        Args:
            cluster_config: Cluster configuration
            metrics_collector: Resource metrics collector
            resource_sharing_manager: Resource sharing manager for allocations
            default_boost_duration: Default duration for boosts if not specified
            persistence: Optional persistence instance. If None, creates default.
        """
        self.cluster_config = cluster_config
        self.metrics_collector = metrics_collector
        self.resource_sharing_manager = resource_sharing_manager
        self.default_boost_duration = default_boost_duration
        
        # Initialize persistence
        self._persistence = persistence or ResourceBoostPersistence()
        
        # Track active boosts
        self._active_boosts: Dict[str, ResourceBoost] = {}
        
        # Ray custom resources for boosts
        self._boosted_resources: Dict[str, Dict[str, float]] = {}
        
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the boost manager."""
        if self._initialized:
            return
            
        # Ensure Ray is connected
        if not ray.is_initialized():
            ray.init(address="auto")
        
        # Load existing boosts from persistence
        await self._load_boosts_from_persistence()
            
        self._initialized = True
        logger.info("Resource boost manager initialized")
    
    async def request_boost(self, request: ResourceBoostRequest) -> Optional[str]:
        """Request a resource boost.
        
        Args:
            request: The boost request details
            
        Returns:
            The boost ID if successful, None otherwise
        """
        if not self._initialized:
            await self.initialize()
            
        boost_id = str(uuid.uuid4())
        
        try:
            # Find suitable source node with available resources
            source_node = await self._find_source_node(
                request.target_node,
                request.resource_type,
                request.amount,
                request.preferred_source
            )
            
            if not source_node:
                logger.warning(f"No suitable source node found for boost request: {request}")
                return None
            
            # Calculate expiry time
            expires_at = None
            if request.duration_seconds:
                expires_at = datetime.now(UTC) + timedelta(seconds=request.duration_seconds)
            else:
                expires_at = datetime.now(UTC) + self.default_boost_duration
            
            # Create the boost record
            boost = ResourceBoost(
                boost_id=boost_id,
                source_node=source_node,
                target_node=request.target_node,
                resource_type=request.resource_type,
                amount=request.amount,
                allocated_at=datetime.now(UTC),
                expires_at=expires_at,
            )
            
            # Allocate resources using resource sharing manager
            # Convert duration to timedelta if provided
            duration = None
            if request.duration_seconds:
                duration = timedelta(seconds=request.duration_seconds)
                
            allocation_id = await self.resource_sharing_manager.request_resource(
                node_id=source_node,
                resource_type=request.resource_type,
                amount=request.amount,
                priority=request.priority,
                duration=duration,
            )
            
            logger.info(f"Resource allocation ID: {allocation_id}")
            
            if not allocation_id:
                logger.error(f"Failed to allocate resources for boost {boost_id}")
                return None
            
            # Store the boost
            self._active_boosts[boost_id] = boost
            
            # Save to persistence
            await self._save_boosts_to_persistence()
            
            # Add the resources to Ray's resource pool on target node
            try:
                await self._add_ray_resources(boost)
            except Exception as e:
                # Log warning but don't fail the boost
                logger.warning(f"Failed to add Ray resources for boost {boost_id}: {e}")
                logger.info("Boost is still active but Ray resource scheduling is disabled")
            
            logger.info(f"Resource boost created: {boost_id} "
                       f"({request.amount} {request.resource_type.value} "
                       f"from {source_node} to {request.target_node})")
            
            return boost_id
            
        except Exception as e:
            logger.error(f"Failed to request resource boost: {e}")
            return None
    
    async def release_boost(self, boost_id: str) -> bool:
        """Release an active resource boost.
        
        Args:
            boost_id: The boost ID to release
            
        Returns:
            True if successful, False otherwise
        """
        if boost_id not in self._active_boosts:
            logger.warning(f"Boost {boost_id} not found in active boosts")
            return False
            
        boost = self._active_boosts[boost_id]
        
        try:
            # Remove from Ray resources
            await self._remove_ray_resources(boost)
            
            # Mark as inactive
            boost.is_active = False
            
            # Clean up from active boosts
            del self._active_boosts[boost_id]
            
            # Update persistence
            await self._save_boosts_to_persistence()
            
            logger.info(f"Resource boost released: {boost_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to release boost {boost_id}: {e}")
            return False
    
    async def get_active_boosts(self, target_node: Optional[str] = None) -> List[ResourceBoost]:
        """Get list of active boosts.
        
        Args:
            target_node: Optional filter for specific target node
            
        Returns:
            List of active boosts
        """
        boosts = list(self._active_boosts.values())
        
        if target_node:
            boosts = [b for b in boosts if b.target_node == target_node]
            
        return sorted(boosts, key=lambda b: b.allocated_at, reverse=True)
    
    async def get_boost_status(self) -> Dict[str, Any]:
        """Get overall boost status.
        
        Returns:
            Dictionary with boost statistics
        """
        active_boosts = await self.get_active_boosts()
        
        # Aggregate by resource type
        boosted_by_type = {}
        total_boosted = {}
        
        for boost in active_boosts:
            rtype = boost.resource_type.value
            if rtype not in boosted_by_type:
                boosted_by_type[rtype] = 0
                total_boosted[rtype] = 0
            
            boosted_by_type[rtype] += boost.amount
            total_boosted[rtype] += boost.amount
        
        return {
            "total_active_boosts": len(active_boosts),
            "boosted_resources": boosted_by_type,
            "total_boosted_amount": total_boosted,
            "boosts": [
                {
                    "boost_id": boost.boost_id,
                    "source_node": boost.source_node,
                    "target_node": boost.target_node,
                    "resource_type": boost.resource_type.value,
                    "amount": boost.amount,
                    "allocated_at": boost.allocated_at.isoformat(),
                    "expires_at": boost.expires_at.isoformat() if boost.expires_at else None,
                }
                for boost in active_boosts
            ]
        }
    
    async def cleanup_expired_boosts(self) -> int:
        """Clean up expired boosts.
        
        Returns:
            Number of boosts cleaned up
        """
        now = datetime.now(UTC)
        expired_boosts = [
            boost_id for boost_id, boost in self._active_boosts.items()
            if boost.expires_at and boost.expires_at < now
        ]
        
        for boost_id in expired_boosts:
            await self.release_boost(boost_id)
            
        # Also clean up expired boosts in persistence that might not be in memory
        await self._cleanup_expired_boosts_in_persistence()
            
        if expired_boosts:
            logger.info(f"Cleaned up {len(expired_boosts)} expired boosts")
            
        return len(expired_boosts)
    
    async def _find_source_node(
        self,
        target_node: str,
        resource_type: ResourceType,
        amount: float,
        preferred_source: Optional[str] = None,
    ) -> Optional[str]:
        """Find a suitable source node with available resources.
        
        Args:
            target_node: Node requesting the boost
            resource_type: Type of resource needed
            amount: Amount of resource needed
            preferred_source: Preferred source node if any
            
        Returns:
            Source node ID if found, None otherwise
        """
        # If preferred source is specified, try it first
        if preferred_source:
            if await self._can_supply_resource(preferred_source, resource_type, amount):
                return preferred_source
        
        # Get all nodes except the target
        available_nodes = [
            node.name for node in self.cluster_config.nodes
            if node.name != target_node
        ]
        
        # Check each node for availability
        for node_id in available_nodes:
            if await self._can_supply_resource(node_id, resource_type, amount):
                return node_id
                
        return None
    
    async def _can_supply_resource(
        self,
        node_id: str,
        resource_type: ResourceType,
        amount: float,
    ) -> bool:
        """Check if a node can supply the requested resource amount.
        
        Args:
            node_id: Node to check
            resource_type: Type of resource
            amount: Amount needed
            
        Returns:
            True if node can supply the resource
        """
        # Get current resource snapshots
        snapshot = self.metrics_collector.get_all_latest_snapshots().get(node_id)
        if not snapshot:
            return False
            
        # Check available resources based on type
        if resource_type == ResourceType.CPU:
            available = snapshot.cpu_available
            return available >= amount
        elif resource_type == ResourceType.GPU:
            available = snapshot.gpu_available
            return available >= amount
        elif resource_type == ResourceType.MEMORY:
            available = snapshot.memory_available
            return available >= (amount * 1024**3)  # Convert GB to bytes
            
        return False
    
    async def _add_ray_resources(self, boost: ResourceBoost) -> None:
        """Add boosted resources to Ray's resource pool.
        
        Args:
            boost: The boost to add to Ray resources
        """
        # Create a custom resource name for the boost
        resource_name = f"boost_{boost.resource_type.value.lower()}_{boost.boost_id[:8]}"
        
        # Add the resource to Ray cluster-wide
        ray.experimental.set_resource(resource_name, boost.amount)
        
        # Also add to the target node's specific resource pool if it's a GPU boost
        if boost.resource_type == ResourceType.GPU:
            # For GPU boosts, we can create a placement group to ensure resources
            # are available on the target node
            from ray.util.placement_group import placement_group
            import uuid
            
            pg_name = f"boost_pg_{boost.boost_id[:8]}"
            bundles = {
                boost.target_node: {f"GPU": boost.amount}
            }
            
            try:
                # Create a placement group to reserve GPU on target node
                pg = placement_group(bundles, strategy="STRICT_SPREAD", name=pg_name)
                ray.get(pg.ready())
                boost.ray_placement_group = pg_name
                logger.info(f"Created placement group {pg_name} for GPU boost on {boost.target_node}")
            except Exception as e:
                logger.warning(f"Failed to create placement group for GPU boost: {e}")
        
        # Track the added resource
        if boost.target_node not in self._boosted_resources:
            self._boosted_resources[boost.target_node] = {}
        self._boosted_resources[boost.target_node][resource_name] = boost.amount
        
        logger.info(f"Added Ray resource: {resource_name}={boost.amount} "
                   f"to {boost.target_node}")
    
    async def _remove_ray_resources(self, boost: ResourceBoost) -> None:
        """Remove boosted resources from Ray's resource pool.
        
        Args:
            boost: The boost to remove from Ray resources
        """
        # Find and remove the custom resource
        target_resources = self._boosted_resources.get(boost.target_node, {})
        
        for resource_name, amount in target_resources.items():
            if f"boost_{boost.resource_type.value.lower()}_{boost.boost_id[:8]}" in resource_name:
                # Remove the resource (set to 0)
                ray.experimental.set_resource(resource_name, 0)
                del target_resources[resource_name]
                break
        
        # Remove placement group if it exists
        if boost.ray_placement_group:
            try:
                from ray.util.placement_group import remove_placement_group
                remove_placement_group(boost.ray_placement_group)
                logger.info(f"Removed placement group {boost.ray_placement_group}")
            except Exception as e:
                logger.warning(f"Failed to remove placement group: {e}")
        
        logger.info(f"Removed Ray resources for boost {boost.boost_id}")
    
    async def _load_boosts_from_persistence(self) -> None:
        """Load boosts from persistence and restore them to memory."""
        try:
            boost_dicts = self._persistence.load_boosts()
            
            for boost_dict in boost_dicts:
                # Only load active boosts that haven't expired
                if not boost_dict.get('is_active', True):
                    continue
                    
                # Check if boost has expired
                if boost_dict.get('expires_at'):
                    if isinstance(boost_dict['expires_at'], datetime):
                        if boost_dict['expires_at'] < datetime.now(UTC):
                            continue  # Skip expired boosts
                
                # Reconstruct ResourceBoost object
                boost = ResourceBoost(
                    boost_id=boost_dict['boost_id'],
                    source_node=boost_dict['source_node'],
                    target_node=boost_dict['target_node'],
                    resource_type=boost_dict['resource_type'],
                    amount=boost_dict['amount'],
                    allocated_at=boost_dict['allocated_at'],
                    expires_at=boost_dict.get('expires_at'),
                    ray_placement_group=boost_dict.get('ray_placement_group'),
                    is_active=boost_dict.get('is_active', True)
                )
                
                # Restore to active boosts
                self._active_boosts[boost.boost_id] = boost
                
                # Restore Ray resources tracking if present
                if boost.target_node not in self._boosted_resources:
                    self._boosted_resources[boost.target_node] = {}
                
            logger.info(f"Loaded {len(self._active_boosts)} boosts from persistence")
            
        except Exception as e:
            logger.error(f"Failed to load boosts from persistence: {e}")
    
    async def _save_boosts_to_persistence(self) -> None:
        """Save current active boosts to persistence."""
        try:
            boost_dicts = []
            for boost in self._active_boosts.values():
                boost_dict = {
                    'boost_id': boost.boost_id,
                    'source_node': boost.source_node,
                    'target_node': boost.target_node,
                    'resource_type': boost.resource_type,
                    'amount': boost.amount,
                    'allocated_at': boost.allocated_at,
                    'expires_at': boost.expires_at,
                    'ray_placement_group': boost.ray_placement_group,
                    'is_active': boost.is_active
                }
                boost_dicts.append(boost_dict)
            
            self._persistence.save_boosts(boost_dicts)
            
        except Exception as e:
            logger.error(f"Failed to save boosts to persistence: {e}")
    
    async def _cleanup_expired_boosts_in_persistence(self) -> None:
        """Clean up expired boosts in persistence file."""
        try:
            boost_dicts = self._persistence.load_boosts()
            now = datetime.now(UTC)
            
            # Filter out expired boosts
            active_boosts = []
            for boost_dict in boost_dicts:
                if not boost_dict.get('is_active', True):
                    continue
                    
                if boost_dict.get('expires_at'):
                    if isinstance(boost_dict['expires_at'], datetime):
                        if boost_dict['expires_at'] < now:
                            continue  # Skip expired boosts
                
                active_boosts.append(boost_dict)
            
            # Save back the filtered list
            self._persistence.save_boosts(active_boosts)
            
            cleaned_count = len(boost_dicts) - len(active_boosts)
            if cleaned_count > 0:
                logger.debug(f"Cleaned up {cleaned_count} expired boosts from persistence")
                
        except Exception as e:
            logger.error(f"Failed to cleanup expired boosts in persistence: {e}")
