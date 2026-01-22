"""Main orchestration logic for the distributed grid."""

from __future__ import annotations

import asyncio
from datetime import datetime, UTC
from typing import Dict, List, Optional

import structlog
from pydantic import BaseModel

from distributed_grid.config import ClusterConfig, NodeConfig
from distributed_grid.core.executor import GridExecutor
from distributed_grid.core.health_checker import HealthChecker
from distributed_grid.core.ssh_manager import SSHManager
from distributed_grid.orchestration.resource_sharing import (
    ResourceSharingManager,
    ResourceRequest,
    ResourceType,
)

logger = structlog.get_logger(__name__)


class NodeStatus(BaseModel):
    """Status of a node in the cluster."""
    
    name: str
    is_online: bool
    gpu_count: int
    memory_gb: int
    last_check: datetime
    load_average: Optional[List[float]] = None
    gpu_utilization: Optional[List[float]] = None


class ClusterStatus(BaseModel):
    """Overall cluster status."""
    
    name: str
    total_nodes: int
    online_nodes: int
    total_gpus: int
    available_gpus: int
    nodes: List[NodeStatus]
    last_update: datetime


class GridOrchestrator:
    """Main orchestrator for the distributed grid."""
    
    def __init__(self, config: ClusterConfig) -> None:
        """Initialize the orchestrator."""
        self.config = config
        self.ssh_manager = SSHManager(config.nodes)
        self.health_checker = HealthChecker(self.ssh_manager)
        self.executor = GridExecutor(self.ssh_manager, config.execution)
        self.resource_sharing = ResourceSharingManager(
            self.ssh_manager,
            check_interval=config.resource_sharing.check_interval,
            offer_expiry=config.resource_sharing.offer_expiry,
        )
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the orchestrator and establish connections."""
        logger.info("Initializing grid orchestrator", cluster=self.config.name)
        
        # Initialize SSH connections
        await self.ssh_manager.initialize()
        
        # Check initial health
        await self.health_checker.check_all_nodes()
        
        # Start resource sharing manager
        await self.resource_sharing.start()
        
        self._initialized = True
        logger.info("Grid orchestrator initialized successfully")
    
    async def get_status(self) -> ClusterStatus:
        """Get the current status of the cluster."""
        if not self._initialized:
            raise RuntimeError("Orchestrator not initialized")
        
        health_results = await self.health_checker.check_all_nodes()
        
        nodes = []
        total_gpus = 0
        online_nodes = 0
        
        for node_config, health in zip(self.config.nodes, health_results):
            node_status = NodeStatus(
                name=node_config.name,
                is_online=health.is_online,
                gpu_count=node_config.gpu_count,
                memory_gb=node_config.memory_gb,
                last_check=datetime.now(UTC),
                load_average=health.load_average,
                gpu_utilization=health.gpu_utilization,
            )
            nodes.append(node_status)
            total_gpus += node_config.gpu_count
            if health.is_online:
                online_nodes += 1
        
        return ClusterStatus(
            name=self.config.name,
            total_nodes=len(self.config.nodes),
            online_nodes=online_nodes,
            total_gpus=total_gpus,
            available_gpus=total_gpus,  # TODO: Track actual GPU availability
            nodes=nodes,
            last_update=datetime.now(UTC),
        )
    
    async def run_command(
        self,
        command: str,
        nodes: Optional[int] = None,
        gpus_per_node: Optional[int] = None,
        node_names: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        """Run a command on the cluster."""
        if not self._initialized:
            raise RuntimeError("Orchestrator not initialized")
        
        # Determine which nodes to use
        if node_names:
            selected_nodes = [
                n for n in self.config.nodes if n.name in node_names
            ]
        else:
            # Select nodes based on availability
            selected_nodes = await self._select_nodes(
                count=nodes or self.config.execution.default_nodes,
                gpus_per_node=gpus_per_node or self.config.execution.default_gpus_per_node,
            )
        
        if not selected_nodes:
            raise RuntimeError("No suitable nodes available")
        
        # Execute the command
        results = await self.executor.execute_on_nodes(command, selected_nodes)
        return results
    
    async def _select_nodes(
        self,
        count: int,
        gpus_per_node: int,
    ) -> List[NodeConfig]:
        """Select the best nodes for execution."""
        # Get current status
        status = await self.get_status()
        
        # Filter online nodes with enough GPUs
        suitable_nodes = [
            node for node in status.nodes
            if node.is_online and node.gpu_count >= gpus_per_node
        ]
        
        if len(suitable_nodes) < count:
            raise RuntimeError(
                f"Not enough suitable nodes: need {count}, have {len(suitable_nodes)}"
            )
        
        # Sort by availability (simple strategy - could be more sophisticated)
        suitable_nodes.sort(key=lambda n: n.gpu_utilization[0] if n.gpu_utilization else 0)
        
        # Get the full node configs for the selected nodes
        selected_names = [n.name for n in suitable_nodes[:count]]
        return [n for n in self.config.nodes if n.name in selected_names]
    
    async def run_with_shared_resources(
        self,
        command: str,
        resource_type: ResourceType,
        amount: int,
        priority: str = "medium",
        max_wait_time: int = 300,
        job_id: Optional[str] = None,
        preferred_nodes: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        """Run a command using shared resources from any available node."""
        if not self._initialized:
            raise RuntimeError("Orchestrator not initialized")
        
        # Create resource request
        request = ResourceRequest(
            request_id=job_id or f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            resource_type=resource_type,
            amount=amount,
            priority=priority,
            max_wait_time=max_wait_time,
            preferred_nodes=preferred_nodes,
        )
        
        # Execute using shared resources
        success, output = await self.resource_sharing.execute_on_shared_resources(
            request,
            command,
        )
        
        if not success:
            raise RuntimeError(f"Failed to execute command: {output}")
        
        return {"output": output}
    
    async def get_shared_resource_status(self) -> Dict[str, List[Dict]]:
        """Get the status of shared resources."""
        if not self._initialized:
            raise RuntimeError("Orchestrator not initialized")
        
        return {
            "offers": self.resource_sharing.get_resource_offers(),
            "allocations": self.resource_sharing.get_active_allocations(),
        }
    
    async def shutdown(self) -> None:
        """Shutdown the orchestrator and clean up resources."""
        logger.info("Shutting down grid orchestrator")
        
        if self._initialized:
            # Stop resource sharing manager
            await self.resource_sharing.stop()
            
            await self.ssh_manager.close_all()
            self._initialized = False
        
        logger.info("Grid orchestrator shutdown complete")
