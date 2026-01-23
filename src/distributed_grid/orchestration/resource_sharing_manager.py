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
from distributed_grid.orchestration.resource_sharing_types import (
    SharingPolicy,
    ResourceRequest,
    ResourceAllocation,
    AllocationPriority,
)
from distributed_grid.orchestration.resource_sharing_persistence import (
    ResourceSharingPersistence,
)

logger = structlog.get_logger(__name__)


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
        
        # Resource tracking - now using persistent actor
        self._shared_resources: Dict[str, Dict[ResourceType, float]] = {}
        self._resource_requests: List[ResourceRequest] = []
        self._active_allocations: List[ResourceAllocation] = []
        
        # Ray actor for persistent state (replaced with file persistence)
        self._state_actor = None
        self._persistence = ResourceSharingPersistence()
        
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
        
        # Initialize persistent state actor (disabled for now due to import issues)
        # await ensure_actor_initialized()
        # self._state_actor = get_state_actor()
        self._state_actor = None
        
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
        # Load from file persistence
        actor_resources = self._persistence.load_shared_resources()
        if actor_resources:
            # Convert string keys back to ResourceType enums
            self._shared_resources = {}
            for node_id, resources in actor_resources.items():
                self._shared_resources[node_id] = {
                    ResourceType.CPU: resources.get("CPU", 0.0),
                    ResourceType.GPU: resources.get("GPU", 0.0),
                    ResourceType.MEMORY: resources.get("MEMORY", 0.0),
                }
            return
        
        # Initialize from config
        for node in self.cluster_config.nodes:
            self._shared_resources[node.name] = {
                ResourceType.CPU: 0.0,
                ResourceType.GPU: 0.0,
                ResourceType.MEMORY: 0.0,
            }
            # Save to file
            self._save_shared_resources()
            
    def _save_shared_resources(self) -> None:
        """Save shared resources to file."""
        # Convert to JSON-serializable format
        serializable = {}
        for node_id, resources in self._shared_resources.items():
            serializable[node_id] = {
                "CPU": resources.get(ResourceType.CPU, 0.0),
                "GPU": resources.get(ResourceType.GPU, 0.0),
                "MEMORY": resources.get(ResourceType.MEMORY, 0.0),
            }
        self._persistence.save_shared_resources(serializable)

    def _compute_live_shared_resources(
        self,
        snapshots: Dict[str, ResourceSnapshot],
        threshold: float = 0.2,
    ) -> Dict[str, Dict[ResourceType, float]]:
        shared_resources: Dict[str, Dict[ResourceType, float]] = {}

        # Start from current availability snapshots (best-effort).
        for node_id, snapshot in snapshots.items():
            # Share only a portion of available resources to avoid starving the donor.
            cpu_shareable = max(0.0, snapshot.cpu_available * (1 - threshold))
            gpu_shareable = max(0.0, float(snapshot.gpu_available) * (1 - threshold))
            mem_shareable_gb = max(0.0, (snapshot.memory_available / (1024**3)) * (1 - threshold))

            shared_resources[node_id] = {
                ResourceType.CPU: cpu_shareable,
                ResourceType.GPU: gpu_shareable,
                ResourceType.MEMORY: mem_shareable_gb,
            }

        # Subtract currently active allocations from the donor (source) node so pool reflects remaining shareable.
        for alloc in self._active_allocations:
            if alloc.source_node not in shared_resources:
                continue
            current = shared_resources[alloc.source_node].get(alloc.resource_type, 0.0)
            shared_resources[alloc.source_node][alloc.resource_type] = max(0.0, current - float(alloc.amount))

        return shared_resources

    @staticmethod
    def _normalize_resource_type(raw: Any) -> str:
        if raw is None:
            return ""
        value = str(raw)
        if "." in value:
            value = value.split(".")[-1]
        return value.upper()
            
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

        # Keep shared resource pool up-to-date for status/inspection (and persist as fallback).
        self._shared_resources = self._compute_live_shared_resources(snapshots)
        self._save_shared_resources()
        
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
        # Load requests from persistence
        if not self._resource_requests:  # Only load if empty
            persisted_allocations = self._persistence.load_allocations()
            # Convert persisted allocations to ResourceAllocation objects
            from distributed_grid.monitoring.resource_metrics import ResourceType
            from distributed_grid.orchestration.resource_sharing_types import ResourceAllocation
            
            self._active_allocations = []
            for alloc_data in persisted_allocations:
                resource_type_raw = alloc_data.get("resource_type")
                resource_type_value = self._normalize_resource_type(resource_type_raw)
                allocation = ResourceAllocation(
                    allocation_id=alloc_data["allocation_id"],
                    request_id=alloc_data["request_id"],
                    source_node=alloc_data["source_node"],
                    target_node=alloc_data["target_node"],
                    resource_type=ResourceType(resource_type_value),
                    amount=alloc_data["amount"],
                    allocated_at=datetime.fromisoformat(alloc_data["allocated_at"]),
                    lease_duration=None,  # Could be restored from data if needed
                )
                self._active_allocations.append(allocation)
            
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
                # Remove from persistent actor
                self._save_allocations()
                
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
            
            # Store in persistent actor
            self._save_allocations()
            
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
        
        # Store in persistent actor
        self._save_allocations()
        
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
        
    def _save_allocations(self) -> None:
        """Save allocations to file."""
        # Convert to JSON-serializable format
        serializable = []
        for alloc in self._active_allocations:
            serializable.append({
                "allocation_id": alloc.allocation_id,
                "request_id": alloc.request_id,
                "source_node": alloc.source_node,
                "target_node": alloc.target_node,
                "resource_type": alloc.resource_type.value,
                "amount": alloc.amount,
                "allocated_at": alloc.allocated_at.isoformat(),
            })
        self._persistence.save_allocations(serializable)
    def get_resource_status(self) -> Dict[str, Any]:
        """Get the current status of resource sharing."""
        # Load allocations from persistence for latest state.
        persisted_allocations = self._persistence.load_allocations()
        persisted_resources = self._persistence.load_shared_resources()

        # Refresh active allocations from persistence (best-effort) to keep derived views current.
        self._active_allocations = []
        from distributed_grid.monitoring.resource_metrics import ResourceType
        from distributed_grid.orchestration.resource_sharing_types import ResourceAllocation
        for alloc_data in persisted_allocations:
            resource_type_value = self._normalize_resource_type(alloc_data.get("resource_type"))
            try:
                resource_type = ResourceType(resource_type_value)
            except Exception:
                continue

            self._active_allocations.append(
                ResourceAllocation(
                    allocation_id=alloc_data["allocation_id"],
                    request_id=alloc_data["request_id"],
                    source_node=alloc_data["source_node"],
                    target_node=alloc_data["target_node"],
                    resource_type=resource_type,
                    amount=alloc_data["amount"],
                    allocated_at=datetime.fromisoformat(alloc_data["allocated_at"]),
                    lease_duration=None,
                )
            )
        
        # Transform allocations to expected format
        active_allocations = {}
        for alloc in persisted_allocations:
            resource_type_value = self._normalize_resource_type(alloc.get("resource_type"))
            active_allocations[alloc["allocation_id"]] = {
                "node_id": alloc["target_node"],
                "resource_type": resource_type_value,
                "amount": alloc["amount"],
                "priority": "normal",
                "expires_at": "never",  # Could be restored from data if needed
            }
        
        # Prefer live metrics-derived pool if available; otherwise fall back to persisted pool.
        snapshots = self.metrics_collector.get_all_latest_snapshots()
        if snapshots:
            shared_resources = self._compute_live_shared_resources(snapshots)
            self._save_shared_resources()
        else:
            shared_resources = {}
            for node_id, resources in persisted_resources.items():
                shared_resources[node_id] = {
                    ResourceType.CPU: resources.get("CPU", 0.0),
                    ResourceType.GPU: resources.get("GPU", 0.0),
                    ResourceType.MEMORY: resources.get("MEMORY", 0.0),
                }
        
        return {
            "policy": self.policy,
            "pending_requests_count": 0,  # Could be tracked if needed
            "active_allocations": active_allocations,
            "shared_resources": shared_resources,
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
