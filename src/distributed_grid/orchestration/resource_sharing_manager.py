"""Resource sharing manager for intelligent resource allocation across the Ray cluster."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, UTC, timedelta
from typing import Dict, List, Optional, Tuple, Any, Set
from enum import Enum
import math

import ray
import structlog
from ray.util.placement_group import PlacementGroup

from distributed_grid.monitoring.resource_metrics import (
    ResourceMetricsCollector,
    ResourceSnapshot,
    ResourceType,
    ResourceTrend,
)
from distributed_grid.config import ClusterConfig, NodeConfig

logger = structlog.get_logger(__name__)


class SharingPolicy(str, Enum):
    """Resource sharing policies."""
    CONSERVATIVE = "conservative"  # Only share excess resources
    BALANCED = "balanced"  # Share resources based on pressure
    AGGRESSIVE = "aggressive"  # Proactively share resources
    PREDICTIVE = "predictive"  # Use predictions to anticipate needs


class AllocationPriority(int, Enum):
    """Priority levels for resource allocation."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class ResourceRequest:
    """A request for shared resources."""
    request_id: str
    node_id: str
    resource_type: ResourceType
    amount: float
    priority: AllocationPriority
    duration: Optional[timedelta] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    timeout: Optional[timedelta] = field(default_factory=lambda: timedelta(minutes=5))
    
    @property
    def is_expired(self) -> bool:
        """Check if the request has expired."""
        return datetime.now(UTC) > self.created_at + self.timeout
    
    @property
    def urgency_score(self) -> float:
        """Calculate urgency score based on priority and wait time."""
        wait_time = (datetime.now(UTC) - self.created_at).total_seconds()
        priority_weight = self.priority.value * 0.7
        time_weight = min(wait_time / 300.0, 1.0) * 0.3  # Normalize to 5 minutes
        return priority_weight + time_weight


@dataclass
class ResourceAllocation:
    """An allocation of shared resources."""
    allocation_id: str
    request_id: str
    source_node: str
    target_node: str
    resource_type: ResourceType
    amount: float
    allocated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    lease_duration: Optional[timedelta] = None
    conditions: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_expired(self) -> bool:
        """Check if the allocation has expired."""
        if not self.lease_duration:
            return False
        return datetime.now(UTC) > self.allocated_at + self.lease_duration


class ResourceSharingManager:
    """Manages intelligent resource sharing across the cluster."""
    
    def __init__(
        self,
        cluster_config: ClusterConfig,
        metrics_collector: ResourceMetricsCollector,
        policy: SharingPolicy = SharingPolicy.BALANCED,
        rebalance_interval: float = 30.0,
        allocation_timeout: timedelta = timedelta(minutes=10),
    ):
        """Initialize the resource sharing manager."""
        self.cluster_config = cluster_config
        self.metrics_collector = metrics_collector
        self.policy = policy
        self.rebalance_interval = rebalance_interval
        self.allocation_timeout = allocation_timeout
        
        # Resource tracking
        self._shared_resources: Dict[str, Dict[ResourceType, float]] = {}
        self._resource_requests: List[ResourceRequest] = []
        self._active_allocations: List[ResourceAllocation] = []
        
        # Node roles and priorities
        self._node_priorities: Dict[str, float] = {}
        self._master_node = self._find_master_node()
        
        # Rebalancing task
        self._rebalance_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Ray placement groups for shared resources
        self._placement_groups: Dict[str, PlacementGroup] = {}
        
        # Initialize node priorities
        self._initialize_node_priorities()
        
    def _find_master_node(self) -> str:
        """Find the master node in the cluster."""
        for node in self.cluster_config.nodes:
            if node.role == "master":
                return node.name
        return self.cluster_config.nodes[0].name if self.cluster_config.nodes else ""
        
    def _initialize_node_priorities(self) -> None:
        """Initialize priority weights for nodes."""
        for node in self.cluster_config.nodes:
            if node.role == "master":
                self._node_priorities[node.name] = 1.0  # Master gets highest priority
            elif node.role == "worker":
                # Priority based on resources
                resource_score = (node.gpu_count * 0.5 + node.memory_gb / 64.0 * 0.3 + 0.2)
                self._node_priorities[node.name] = resource_score
                
    async def start(self) -> None:
        """Start the resource sharing manager."""
        if self._running:
            return
            
        self._running = True
        logger.info("Starting resource sharing manager", policy=self.policy)
        
        # Initialize shared resource pools
        await self._initialize_shared_resources()
        
        # Start rebalancing loop
        self._rebalance_task = asyncio.create_task(self._rebalancing_loop())
        
    async def stop(self) -> None:
        """Stop the resource sharing manager."""
        self._running = False
        
        if self._rebalance_task:
            self._rebalance_task.cancel()
            try:
                await self._rebalance_task
            except asyncio.CancelledError:
                pass
                
        # Clean up placement groups
        for pg in self._placement_groups.values():
            try:
                ray.remove_placement_group(pg)
            except Exception:
                pass
                
        self._placement_groups.clear()
        logger.info("Resource sharing manager stopped")
        
    async def _initialize_shared_resources(self) -> None:
        """Initialize shared resource pools."""
        for node in self.cluster_config.nodes:
            self._shared_resources[node.name] = {
                ResourceType.CPU: 0.0,
                ResourceType.GPU: 0.0,
                ResourceType.MEMORY: 0.0,
            }
            
    async def _rebalancing_loop(self) -> None:
        """Main rebalancing loop."""
        while self._running:
            try:
                await self._rebalance_resources()
                await asyncio.sleep(self.rebalance_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in rebalancing loop", error=str(e))
                await asyncio.sleep(5)
                
    async def _rebalance_resources(self) -> None:
        """Rebalance resources across the cluster."""
        # Get current resource snapshots
        snapshots = self.metrics_collector.get_all_latest_snapshots()
        
        if not snapshots:
            return
            
        # Clean up expired requests and allocations
        await self._cleanup_expired()
        
        # Process pending requests
        await self._process_resource_requests(snapshots)
        
        # Proactively rebalance based on policy
        if self.policy in [SharingPolicy.AGGRESSIVE, SharingPolicy.PREDICTIVE]:
            await self._proactive_rebalancing(snapshots)
            
    async def _cleanup_expired(self) -> None:
        """Clean up expired requests and allocations."""
        # Remove expired requests
        self._resource_requests = [
            r for r in self._resource_requests
            if not r.is_expired
        ]
        
        # Remove expired allocations
        expired_allocations = [
            a for a in self._active_allocations
            if a.is_expired
        ]
        
        for allocation in expired_allocations:
            await self._release_allocation(allocation)
            
    async def _process_resource_requests(self, snapshots: Dict[str, ResourceSnapshot]) -> None:
        """Process pending resource requests."""
        if not self._resource_requests:
            return
            
        # Sort requests by urgency
        sorted_requests = sorted(
            self._resource_requests,
            key=lambda r: r.urgency_score,
            reverse=True,
        )
        
        for request in sorted_requests:
            if await self._fulfill_request(request, snapshots):
                self._resource_requests.remove(request)
                
    async def _fulfill_request(
        self,
        request: ResourceRequest,
        snapshots: Dict[str, ResourceSnapshot],
    ) -> bool:
        """Try to fulfill a resource request."""
        # Find suitable donor nodes
        donors = self._find_donor_nodes(request, snapshots)
        
        if not donors:
            return False
            
        # Select best donor
        best_donor = self._select_best_donor(request, donors)
        
        if not best_donor:
            return False
            
        # Create allocation
        allocation = ResourceAllocation(
            allocation_id=f"alloc_{int(time.time())}_{request.node_id}",
            request_id=request.request_id,
            source_node=best_donor,
            target_node=request.node_id,
            resource_type=request.resource_type,
            amount=request.amount,
            lease_duration=request.duration,
        )
        
        # Execute allocation
        if await self._execute_allocation(allocation):
            self._active_allocations.append(allocation)
            logger.info(
                "Resource allocated",
                allocation_id=allocation.allocation_id,
                source=best_donor,
                target=request.node_id,
                resource=request.resource_type,
                amount=request.amount,
            )
            return True
            
        return False
        
    def _find_donor_nodes(
        self,
        request: ResourceRequest,
        snapshots: Dict[str, ResourceSnapshot],
    ) -> List[str]:
        """Find nodes that can donate resources."""
        donors = []
        
        for node_id, snapshot in snapshots.items():
            if node_id == request.node_id:
                continue  # Can't donate to self
                
            # Check if node has excess resources
            if self._has_excess_resource(snapshot, request.resource_type, request.amount):
                donors.append(node_id)
                
        return donors
        
    def _has_excess_resource(
        self,
        snapshot: ResourceSnapshot,
        resource_type: ResourceType,
        amount: float,
    ) -> bool:
        """Check if a node has excess resources to share."""
        threshold = 0.2  # 20% threshold for excess
        
        if resource_type == ResourceType.CPU:
            excess = snapshot.cpu_available * (1 - threshold)
            return excess >= amount
        elif resource_type == ResourceType.GPU:
            excess = snapshot.gpu_available * (1 - threshold)
            return excess >= amount
        elif resource_type == ResourceType.MEMORY:
            excess = snapshot.memory_available * (1 - threshold)
            return excess >= amount
            
        return False
        
    def _select_best_donor(
        self,
        request: ResourceRequest,
        donors: List[str],
    ) -> Optional[str]:
        """Select the best donor node for a request."""
        if not donors:
            return None
            
        # Get snapshots for donor nodes
        snapshots = self.metrics_collector.get_all_latest_snapshots()
        
        # Score donors based on multiple factors
        donor_scores = []
        
        for donor in donors:
            snapshot = snapshots.get(donor)
            if not snapshot:
                continue
                
            # Factors: resource availability, pressure, priority
            resource_score = 0.0
            if request.resource_type == ResourceType.CPU:
                resource_score = snapshot.cpu_available / snapshot.cpu_count
            elif request.resource_type == ResourceType.GPU:
                resource_score = snapshot.gpu_available / max(snapshot.gpu_count, 1)
            elif request.resource_type == ResourceType.MEMORY:
                resource_score = snapshot.memory_available / snapshot.memory_total
                
            pressure_score = 1.0 - snapshot.overall_pressure
            priority_score = 1.0 - self._node_priorities.get(donor, 0.5)
            
            # Combined score
            total_score = (resource_score * 0.5 + pressure_score * 0.3 + priority_score * 0.2)
            donor_scores.append((donor, total_score))
            
        # Return best donor
        if donor_scores:
            return max(donor_scores, key=lambda x: x[1])[0]
            
        return None
        
    async def _execute_allocation(self, allocation: ResourceAllocation) -> bool:
        """Execute a resource allocation using Ray."""
        try:
            # Create or update placement group for shared resources
            pg_name = f"shared_resources_{allocation.source_node}"
            
            # Define resources for placement group
            bundles = []
            if allocation.resource_type == ResourceType.GPU:
                bundles.append({"GPU": int(allocation.amount)})
            elif allocation.resource_type == ResourceType.CPU:
                bundles.append({"CPU": allocation.amount})
            elif allocation.resource_type == ResourceType.MEMORY:
                bundles.append({"memory": int(allocation.amount * 1024**3)})
                
            if not bundles:
                return False
                
            # Create placement group
            placement_group = ray.util.placement_group(
                bundles,
                strategy="STRICT_SPREAD",
                name=pg_name,
            )
            
            # Wait for placement group to be ready
            ready = ray.get(placement_group.ready(), timeout=10)
            if not ready:
                return False
                
            # Store placement group
            self._placement_groups[allocation.allocation_id] = placement_group
            
            # Update shared resource tracking
            if allocation.source_node not in self._shared_resources:
                self._shared_resources[allocation.source_node] = {}
                
            self._shared_resources[allocation.source_node][allocation.resource_type] = \
                self._shared_resources[allocation.source_node].get(allocation.resource_type, 0) + allocation.amount
                
            return True
            
        except Exception as e:
            logger.error("Failed to execute allocation", allocation_id=allocation.allocation_id, error=str(e))
            return False
            
    async def _release_allocation(self, allocation: ResourceAllocation) -> bool:
        """Release a resource allocation."""
        try:
            # Remove placement group
            if allocation.allocation_id in self._placement_groups:
                ray.remove_placement_group(self._placement_groups[allocation.allocation_id])
                del self._placement_groups[allocation.allocation_id]
                
            # Update shared resource tracking
            if allocation.source_node in self._shared_resources:
                current = self._shared_resources[allocation.source_node].get(allocation.resource_type, 0)
                self._shared_resources[allocation.source_node][allocation.resource_type] = max(0, current - allocation.amount)
                
            # Remove from active allocations
            if allocation in self._active_allocations:
                self._active_allocations.remove(allocation)
                
            logger.info(
                "Resource allocation released",
                allocation_id=allocation.allocation_id,
                source=allocation.source_node,
                target=allocation.target_node,
            )
            
            return True
            
        except Exception as e:
            logger.error("Failed to release allocation", allocation_id=allocation.allocation_id, error=str(e))
            return False
            
    async def _proactive_rebalancing(self, snapshots: Dict[str, ResourceSnapshot]) -> None:
        """Proactively rebalance resources based on trends and predictions."""
        # Get resource trends for all nodes
        for node_id, snapshot in snapshots.items():
            pressure = snapshot.overall_pressure
            
            # If node is under high pressure, request resources
            if pressure > 0.8:
                await self._request_resources_for_node(node_id, snapshot)
            # If node has excess resources, offer to share
            elif pressure < 0.3:
                await self._offer_resources_from_node(node_id, snapshot)
                
    async def _request_resources_for_node(self, node_id: str, snapshot: ResourceSnapshot) -> None:
        """Request resources for a node under pressure."""
        # Determine what resources are needed
        if snapshot.cpu_pressure > 0.8:
            amount = snapshot.cpu_count * 0.5  # Request 50% more CPU
            await self.request_resource(
                node_id=node_id,
                resource_type=ResourceType.CPU,
                amount=amount,
                priority=AllocationPriority.HIGH,
                duration=timedelta(minutes=30),
            )
            
        if snapshot.memory_pressure > 0.8:
            amount = snapshot.memory_total * 0.5  # Request 50% more memory
            await self.request_resource(
                node_id=node_id,
                resource_type=ResourceType.MEMORY,
                amount=amount,
                priority=AllocationPriority.HIGH,
                duration=timedelta(minutes=30),
            )
            
        if snapshot.gpu_pressure > 0.8 and snapshot.gpu_count > 0:
            amount = 1  # Request 1 GPU
            await self.request_resource(
                node_id=node_id,
                resource_type=ResourceType.GPU,
                amount=amount,
                priority=AllocationPriority.CRITICAL,
                duration=timedelta(minutes=15),
            )
            
    async def _offer_resources_from_node(self, node_id: str, snapshot: ResourceSnapshot) -> None:
        """Offer resources from a node with excess capacity."""
        # This would typically notify other nodes of available resources
        # For now, we just log the offer
        logger.info(
            "Node offering resources",
            node=node_id,
            cpu_available=snapshot.cpu_available,
            memory_available_gb=snapshot.memory_available / (1024**3),
            gpu_available=snapshot.gpu_available,
        )
        
    async def request_resource(
        self,
        node_id: str,
        resource_type: ResourceType,
        amount: float,
        priority: AllocationPriority = AllocationPriority.NORMAL,
        duration: Optional[timedelta] = None,
    ) -> str:
        """Request shared resources for a node."""
        request_id = f"req_{int(time.time())}_{node_id}"
        
        request = ResourceRequest(
            request_id=request_id,
            node_id=node_id,
            resource_type=resource_type,
            amount=amount,
            priority=priority,
            duration=duration,
        )
        
        self._resource_requests.append(request)
        
        logger.info(
            "Resource request submitted",
            request_id=request_id,
            node=node_id,
            resource=resource_type,
            amount=amount,
            priority=priority,
        )
        
        return request_id
        
    async def release_resource(self, allocation_id: str) -> bool:
        """Release a previously allocated resource."""
        allocation = None
        for a in self._active_allocations:
            if a.allocation_id == allocation_id:
                allocation = a
                break
                
        if allocation:
            return await self._release_allocation(allocation)
            
        return False
        
    def get_resource_status(self) -> Dict[str, Any]:
        """Get the current status of resource sharing."""
        return {
            "policy": self.policy,
            "pending_requests": len(self._resource_requests),
            "active_allocations": len(self._active_allocations),
            "shared_resources": self._shared_resources,
            "node_priorities": self._node_priorities,
            "master_node": self._master_node,
        }
        
    def get_allocation_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get the history of resource allocations."""
        history = []
        
        for allocation in self._active_allocations[-limit:]:
            history.append({
                "allocation_id": allocation.allocation_id,
                "request_id": allocation.request_id,
                "source_node": allocation.source_node,
                "target_node": allocation.target_node,
                "resource_type": allocation.resource_type,
                "amount": allocation.amount,
                "allocated_at": allocation.allocated_at.isoformat(),
                "lease_duration": allocation.lease_duration.total_seconds() if allocation.lease_duration else None,
            })
            
        return history
