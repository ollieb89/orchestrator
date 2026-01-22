"""Health checker for monitoring cluster nodes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List

from distributed_grid.core.health_checker import HealthChecker
from distributed_grid.schemas.node import Node, NodeStatus


class ClusterHealthChecker:
    """Monitors health of all cluster nodes."""

    def __init__(self, check_interval_seconds: int = 60) -> None:
        """Initialize the health checker."""
        self.check_interval = timedelta(seconds=check_interval_seconds)
        self._health_checker = HealthChecker()
        self._node_statuses: dict[str, NodeStatus] = {}
        self._monitoring = False

    async def start_monitoring(self, nodes: List[Node]) -> None:
        """Start monitoring the given nodes."""
        self._monitoring = True
        
        # Initialize node statuses
        for node in nodes:
            self._node_statuses[node.id] = NodeStatus(
                node_id=node.id,
                status="unknown",
                timestamp=datetime.utcnow(),
            )
        
        # Start monitoring loop
        asyncio.create_task(self._monitoring_loop(nodes))

    async def stop_monitoring(self) -> None:
        """Stop monitoring."""
        self._monitoring = False

    async def get_node_status(self, node_id: str) -> Optional[NodeStatus]:
        """Get the current status of a node."""
        return self._node_statuses.get(node_id)

    async def get_all_statuses(self) -> Dict[str, NodeStatus]:
        """Get all node statuses."""
        return self._node_statuses.copy()

    async def _monitoring_loop(self, nodes: List[Node]) -> None:
        """Main monitoring loop."""
        while self._monitoring:
            # Check all nodes in parallel
            tasks = [
                self._check_node(node)
                for node in nodes
            ]
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Wait for next check
            await asyncio.sleep(self.check_interval.total_seconds())

    async def _check_node(self, node: Node) -> None:
        """Check a single node's health."""
        try:
            # Use existing health checker
            is_healthy = await self._health_checker.check_node(node)
            
            # Get detailed metrics
            metrics = await self._health_checker.get_node_metrics(node)
            
            # Update status
            status = NodeStatus(
                node_id=node.id,
                status="healthy" if is_healthy else "unhealthy",
                timestamp=datetime.utcnow(),
                gpu_utilization=metrics.get("gpu_utilization"),
                memory_utilization=metrics.get("memory_utilization"),
                cpu_utilization=metrics.get("cpu_utilization"),
                disk_usage=metrics.get("disk_usage"),
                temperature=metrics.get("temperature"),
                power_consumption=metrics.get("power_consumption"),
            )
            
            self._node_statuses[node.id] = status
            
        except Exception as e:
            # Mark as unhealthy with error
            self._node_statuses[node.id] = NodeStatus(
                node_id=node.id,
                status="error",
                timestamp=datetime.utcnow(),
                error_message=str(e),
            )
