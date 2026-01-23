"""Intelligent scheduler for cross-node resource allocation and task placement."""

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
from ray.util.placement_group import PlacementGroup, placement_group
from ray.autoscaler._private.util import format_info_string

from distributed_grid.monitoring.resource_metrics import (
    ResourceMetricsCollector,
    ResourceSnapshot,
    ResourceType,
    ResourceTrend,
)
from distributed_grid.orchestration.resource_sharing_manager import (
    ResourceSharingManager,
    AllocationPriority,
)
from distributed_grid.config import ClusterConfig, NodeConfig

logger = structlog.get_logger(__name__)


class SchedulingStrategy(str, Enum):
    """Scheduling strategies for task placement."""
    LOCAL_FIRST = "local_first"  # Try to place on local node first
    BEST_FIT = "best_fit"  # Place on node with best resource fit
    LOAD_BALANCED = "load_balanced"  # Distribute tasks evenly
    COST_OPTIMIZED = "cost_optimized"  # Minimize resource cost
    PERFORMANCE_OPTIMIZED = "performance_optimized"  # Maximize performance


class TaskPriority(int, Enum):
    """Priority levels for tasks."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class ResourceRequirement:
    """Resource requirements for a task."""
    cpu_count: float = 1.0
    memory_mb: int = 1024
    gpu_count: int = 0
    gpu_memory_mb: int = 0
    custom_resources: Dict[str, float] = field(default_factory=dict)
    
    def to_ray_resources(self) -> Dict[str, float]:
        """Convert to Ray resource format."""
        resources = {
            "CPU": self.cpu_count,
        }
        
        if self.memory_mb > 0:
            resources["memory"] = self.memory_mb * 1024 * 1024  # Convert MB to bytes
            
        if self.gpu_count > 0:
            resources["GPU"] = self.gpu_count
            
        resources.update(self.custom_resources)
        return resources


@dataclass
class SchedulingRequest:
    """A request for task scheduling."""
    task_id: str
    requirements: ResourceRequirement
    preferences: Dict[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    strategy: SchedulingStrategy = SchedulingStrategy.BEST_FIT
    deadline: Optional[datetime] = None
    affinity_nodes: List[str] = field(default_factory=list)
    anti_affinity_nodes: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    
    @property
    def is_urgent(self) -> bool:
        """Check if the task is urgent."""
        if self.deadline:
            return datetime.now(UTC) + timedelta(minutes=30) > self.deadline
        return self.priority >= TaskPriority.HIGH


@dataclass
class SchedulingDecision:
    """A scheduling decision for a task."""
    task_id: str
    node_id: str
    placement_group: Optional[PlacementGroup] = None
    bundle_index: int = 0
    shared_resources: Dict[str, float] = field(default_factory=dict)
    estimated_start_time: Optional[datetime] = None
    confidence: float = 0.0
    reasoning: List[str] = field(default_factory=list)


class IntelligentScheduler:
    """Intelligent scheduler for cross-node resource allocation."""
    
    def __init__(
        self,
        cluster_config: ClusterConfig,
        metrics_collector: ResourceMetricsCollector,
        resource_sharing_manager: ResourceSharingManager,
        default_strategy: SchedulingStrategy = SchedulingStrategy.BEST_FIT,
        prediction_window: timedelta = timedelta(minutes=15),
    ):
        """Initialize the intelligent scheduler."""
        self.cluster_config = cluster_config
        self.metrics_collector = metrics_collector
        self.resource_sharing_manager = resource_sharing_manager
        self.default_strategy = default_strategy
        self.prediction_window = prediction_window
        
        # Scheduling state
        self._pending_requests: List[SchedulingRequest] = []
        self._active_tasks: Dict[str, SchedulingDecision] = {}
        self._completed_tasks: List[str] = []
        
        # Node capabilities and preferences
        self._node_capabilities: Dict[str, Dict[str, Any]] = {}
        self._node_preferences: Dict[str, float] = {}
        
        # Performance tracking
        self._task_performance: Dict[str, Dict[str, float]] = {}
        
        # Initialize node capabilities
        self._initialize_node_capabilities()
        
    def _initialize_node_capabilities(self) -> None:
        """Initialize node capabilities based on configuration."""
        for node in self.cluster_config.nodes:
            self._node_capabilities[node.name] = {
                "max_cpu": node.cpu_count,
                "max_memory_gb": node.memory_gb,
                "max_gpu": node.gpu_count,
                "role": node.role,
                "tags": node.tags,
                "network_bandwidth": 1000,  # Mbps, default value
            }
            
            # Set initial preferences based on role
            if node.role == "master":
                self._node_preferences[node.name] = 1.0
            else:
                self._node_preferences[node.name] = 0.8
                
    async def schedule_task(self, request: SchedulingRequest) -> SchedulingDecision:
        """Schedule a task based on its requirements."""
        logger.info(
            "Scheduling task",
            task_id=request.task_id,
            cpu=request.requirements.cpu_count,
            memory_mb=request.requirements.memory_mb,
            gpu=request.requirements.gpu_count,
            priority=request.priority,
        )
        
        # Get current resource snapshots
        snapshots = self.metrics_collector.get_all_latest_snapshots()
        
        # Filter nodes based on constraints
        eligible_nodes = self._filter_eligible_nodes(request, snapshots)
        
        if not eligible_nodes:
            # Try to request shared resources
            if await self._request_shared_resources(request):
                # Retry after getting shared resources
                snapshots = self.metrics_collector.get_all_latest_snapshots()
                eligible_nodes = self._filter_eligible_nodes(request, snapshots)
                
        if not eligible_nodes:
            raise RuntimeError(f"No eligible nodes for task {request.task_id}")
            
        # Select best node based on strategy
        best_node = await self._select_best_node(request, eligible_nodes, snapshots)
        
        # Create scheduling decision
        decision = await self._create_scheduling_decision(request, best_node, snapshots)
        
        # Record the decision
        self._active_tasks[request.task_id] = decision
        
        logger.info(
            "Task scheduled",
            task_id=request.task_id,
            node=decision.node_id,
            confidence=decision.confidence,
        )
        
        return decision
        
    def _filter_eligible_nodes(
        self,
        request: SchedulingRequest,
        snapshots: Dict[str, ResourceSnapshot],
    ) -> List[str]:
        """Filter nodes based on task requirements and constraints."""
        eligible = []
        
        for node_id, snapshot in snapshots.items():
            # Check affinity/anti-affinity
            if request.affinity_nodes and node_id not in request.affinity_nodes:
                continue
                
            if request.anti_affinity_nodes and node_id in request.anti_affinity_nodes:
                continue
                
            # Check resource requirements
            if not self._meets_requirements(snapshot, request.requirements):
                continue
                
            eligible.append(node_id)
            
        return eligible
        
    def _meets_requirements(
        self,
        snapshot: ResourceSnapshot,
        requirements: ResourceRequirement,
    ) -> bool:
        """Check if a node meets task requirements."""
        # CPU requirement
        if snapshot.cpu_available < requirements.cpu_count:
            return False
            
        # Memory requirement
        if snapshot.memory_available < requirements.memory_mb * 1024 * 1024:
            return False
            
        # GPU requirement
        if snapshot.gpu_available < requirements.gpu_count:
            return False
            
        # GPU memory requirement (approximate)
        if requirements.gpu_memory_mb > 0:
            available_gpu_memory = snapshot.gpu_memory_available
            if available_gpu_memory < requirements.gpu_memory_mb * 1024 * 1024:
                return False
                
        # Custom resources
        for resource, amount in requirements.custom_resources.items():
            # Would need to track custom resources in snapshots
            pass
            
        return True
        
    async def _select_best_node(
        self,
        request: SchedulingRequest,
        eligible_nodes: List[str],
        snapshots: Dict[str, ResourceSnapshot],
    ) -> str:
        """Select the best node based on scheduling strategy."""
        if request.strategy == SchedulingStrategy.LOCAL_FIRST:
            return self._select_local_first(request, eligible_nodes)
        elif request.strategy == SchedulingStrategy.BEST_FIT:
            return self._select_best_fit(request, eligible_nodes, snapshots)
        elif request.strategy == SchedulingStrategy.LOAD_BALANCED:
            return self._select_load_balanced(request, eligible_nodes, snapshots)
        elif request.strategy == SchedulingStrategy.COST_OPTIMIZED:
            return self._select_cost_optimized(request, eligible_nodes, snapshots)
        elif request.strategy == SchedulingStrategy.PERFORMANCE_OPTIMIZED:
            return self._select_performance_optimized(request, eligible_nodes, snapshots)
        else:
            return self._select_best_fit(request, eligible_nodes, snapshots)
            
    def _select_local_first(self, request: SchedulingRequest, eligible_nodes: List[str]) -> str:
        """Select local node first if available."""
        # For now, return the first eligible node
        # In a real implementation, would determine the local node
        return eligible_nodes[0] if eligible_nodes else ""
        
    def _select_best_fit(
        self,
        request: SchedulingRequest,
        eligible_nodes: List[str],
        snapshots: Dict[str, ResourceSnapshot],
    ) -> str:
        """Select node with best resource fit."""
        best_node = None
        best_score = -1
        
        for node_id in eligible_nodes:
            snapshot = snapshots[node_id]
            
            # Calculate fit score
            cpu_fit = snapshot.cpu_available / max(request.requirements.cpu_count, 1)
            memory_fit = snapshot.memory_available / max(request.requirements.memory_mb * 1024 * 1024, 1)
            gpu_fit = snapshot.gpu_available / max(request.requirements.gpu_count, 1)
            
            # Combined score (lower is better for best fit)
            score = 1.0 / (cpu_fit * 0.4 + memory_fit * 0.3 + gpu_fit * 0.3)
            
            if score > best_score:
                best_score = score
                best_node = node_id
                
        return best_node or eligible_nodes[0]
        
    def _select_load_balanced(
        self,
        request: SchedulingRequest,
        eligible_nodes: List[str],
        snapshots: Dict[str, ResourceSnapshot],
    ) -> str:
        """Select node to maintain load balance."""
        best_node = None
        lowest_pressure = float('inf')
        
        for node_id in eligible_nodes:
            snapshot = snapshots[node_id]
            pressure = snapshot.overall_pressure
            
            if pressure < lowest_pressure:
                lowest_pressure = pressure
                best_node = node_id
                
        return best_node or eligible_nodes[0]
        
    def _select_cost_optimized(
        self,
        request: SchedulingRequest,
        eligible_nodes: List[str],
        snapshots: Dict[str, ResourceSnapshot],
    ) -> str:
        """Select node with lowest cost."""
        # For now, prefer worker nodes over master
        workers = [n for n in eligible_nodes if self._node_capabilities.get(n, {}).get("role") == "worker"]
        if workers:
            return workers[0]
        return eligible_nodes[0]
        
    def _select_performance_optimized(
        self,
        request: SchedulingRequest,
        eligible_nodes: List[str],
        snapshots: Dict[str, ResourceSnapshot],
    ) -> str:
        """Select node for best performance."""
        best_node = None
        best_score = -1
        
        for node_id in eligible_nodes:
            snapshot = snapshots[node_id]
            capabilities = self._node_capabilities.get(node_id, {})
            
            # Score based on available resources and capabilities
            cpu_score = snapshot.cpu_available / capabilities.get("max_cpu", 1)
            memory_score = snapshot.memory_available / (capabilities.get("max_memory_gb", 1) * 1024**3)
            gpu_score = snapshot.gpu_available / max(capabilities.get("max_gpu", 1), 1)
            
            # Prefer nodes with GPUs for GPU tasks
            if request.requirements.gpu_count > 0:
                gpu_score *= 2.0
                
            total_score = cpu_score * 0.3 + memory_score * 0.3 + gpu_score * 0.4
            
            if total_score > best_score:
                best_score = total_score
                best_node = node_id
                
        return best_node or eligible_nodes[0]
        
    async def _create_scheduling_decision(
        self,
        request: SchedulingRequest,
        node_id: str,
        snapshots: Dict[str, ResourceSnapshot],
    ) -> SchedulingDecision:
        """Create a scheduling decision for a task."""
        decision = SchedulingDecision(
            task_id=request.task_id,
            node_id=node_id,
            estimated_start_time=datetime.now(UTC),
        )
        
        # Create placement group if needed
        if request.requirements.gpu_count > 0 or request.requirements.memory_mb > 4096:
            decision.placement_group = await self._create_placement_group(request, node_id)
            
        # Calculate confidence
        snapshot = snapshots[node_id]
        decision.confidence = self._calculate_confidence(snapshot, request.requirements)
        
        # Add reasoning
        decision.reasoning = self._generate_reasoning(snapshot, request)
        
        return decision
        
    async def _create_placement_group(
        self,
        request: SchedulingRequest,
        node_id: str,
    ) -> Optional[PlacementGroup]:
        """Create a placement group for the task."""
        try:
            bundles = [request.requirements.to_ray_resources()]
            
            pg = placement_group(
                bundles,
                strategy="STRICT_SPREAD",
                name=f"task_{request.task_id}",
            )
            
            # Wait for placement group to be ready
            ready = ray.get(pg.ready(), timeout=10)
            if ready:
                return pg
                
        except Exception as e:
            logger.error("Failed to create placement group", task_id=request.task_id, error=str(e))
            
        return None
        
    def _calculate_confidence(
        self,
        snapshot: ResourceSnapshot,
        requirements: ResourceRequirement,
    ) -> float:
        """Calculate confidence score for the scheduling decision."""
        # Resource utilization factors
        cpu_factor = 1.0 - snapshot.cpu_pressure
        memory_factor = 1.0 - snapshot.memory_pressure
        gpu_factor = 1.0 - snapshot.gpu_pressure
        
        # Overall confidence
        confidence = (cpu_factor * 0.4 + memory_factor * 0.3 + gpu_factor * 0.3)
        
        # Adjust based on resource fit
        if requirements.cpu_count > 0:
            fit = snapshot.cpu_available / requirements.cpu_count
            confidence *= min(fit, 1.0)
            
        return max(0.0, min(1.0, confidence))
        
    def _generate_reasoning(
        self,
        snapshot: ResourceSnapshot,
        request: SchedulingRequest,
    ) -> List[str]:
        """Generate reasoning for the scheduling decision."""
        reasoning = []
        
        if snapshot.cpu_pressure < 0.5:
            reasoning.append("Low CPU utilization")
        elif snapshot.cpu_pressure > 0.8:
            reasoning.append("High CPU utilization")
            
        if snapshot.memory_pressure < 0.5:
            reasoning.append("Sufficient memory available")
        elif snapshot.memory_pressure > 0.8:
            reasoning.append("High memory pressure")
            
        if request.requirements.gpu_count > 0 and snapshot.gpu_available > 0:
            reasoning.append("GPU resources available")
        elif request.requirements.gpu_count > 0:
            reasoning.append("GPU resources required")
            
        if snapshot.overall_pressure < 0.3:
            reasoning.append("Node has low overall load")
        elif snapshot.overall_pressure > 0.8:
            reasoning.append("Node under high load")
            
        return reasoning
        
    async def _request_shared_resources(self, request: SchedulingRequest) -> bool:
        """Request shared resources if local resources are insufficient."""
        try:
            # Determine which resources are needed
            if request.requirements.cpu_count > 1:
                await self.resource_sharing_manager.request_resource(
                    node_id="master",  # Would be actual node ID
                    resource_type=ResourceType.CPU,
                    amount=request.requirements.cpu_count - 1,
                    priority=AllocationPriority.HIGH if request.is_urgent else AllocationPriority.NORMAL,
                )
                
            if request.requirements.memory_mb > 2048:
                await self.resource_sharing_manager.request_resource(
                    node_id="master",
                    resource_type=ResourceType.MEMORY,
                    amount=request.requirements.memory_mb * 1024 * 1024,
                    priority=AllocationPriority.HIGH if request.is_urgent else AllocationPriority.NORMAL,
                )
                
            if request.requirements.gpu_count > 0:
                await self.resource_sharing_manager.request_resource(
                    node_id="master",
                    resource_type=ResourceType.GPU,
                    amount=request.requirements.gpu_count,
                    priority=AllocationPriority.CRITICAL,
                )
                
            return True
            
        except Exception as e:
            logger.error("Failed to request shared resources", task_id=request.task_id, error=str(e))
            return False
            
    async def complete_task(self, task_id: str) -> None:
        """Mark a task as completed and release resources."""
        if task_id in self._active_tasks:
            decision = self._active_tasks[task_id]
            
            # Clean up placement group
            if decision.placement_group:
                try:
                    ray.remove_placement_group(decision.placement_group)
                except Exception:
                    pass
                    
            # Release shared resources
            for resource_type, amount in decision.shared_resources.items():
                if resource_type == "CPU":
                    await self.resource_sharing_manager.release_resource(decision.shared_resources.get("cpu_allocation_id"))
                elif resource_type == "GPU":
                    await self.resource_sharing_manager.release_resource(decision.shared_resources.get("gpu_allocation_id"))
                    
            # Move to completed
            self._completed_tasks.append(task_id)
            del self._active_tasks[task_id]
            
            logger.info("Task completed", task_id=task_id)
            
    def get_scheduling_status(self) -> Dict[str, Any]:
        """Get the current scheduling status."""
        return {
            "pending_requests": len(self._pending_requests),
            "active_tasks": len(self._active_tasks),
            "completed_tasks": len(self._completed_tasks),
            "node_preferences": self._node_preferences,
            "active_task_decisions": {
                task_id: {
                    "node_id": decision.node_id,
                    "confidence": decision.confidence,
                    "estimated_start_time": decision.estimated_start_time.isoformat(),
                }
                for task_id, decision in self._active_tasks.items()
            },
        }
        
    def update_node_preference(self, node_id: str, preference: float) -> None:
        """Update preference score for a node."""
        self._node_preferences[node_id] = max(0.0, min(1.0, preference))
        
    def record_task_performance(
        self,
        task_id: str,
        execution_time: float,
        resource_efficiency: float,
    ) -> None:
        """Record performance metrics for a task."""
        self._task_performance[task_id] = {
            "execution_time": execution_time,
            "resource_efficiency": resource_efficiency,
        }
        
        # Update node preferences based on performance
        if task_id in self._active_tasks:
            node_id = self._active_tasks[task_id].node_id
            current_pref = self._node_preferences.get(node_id, 0.5)
            
            # Adjust preference based on efficiency
            adjustment = (resource_efficiency - 0.5) * 0.1
            new_pref = max(0.0, min(1.0, current_pref + adjustment))
            self._node_preferences[node_id] = new_pref
