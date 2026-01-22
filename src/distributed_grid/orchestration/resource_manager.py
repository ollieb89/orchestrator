"""Resource manager for tracking node resources."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from distributed_grid.schemas.node import Node


@dataclass
class ResourceUsage:
    """Resource usage information."""
    gpu_used: int = 0
    gpu_available: int = 0
    memory_used_gb: float = 0.0
    memory_available_gb: float = 0.0
    cpu_used: int = 0
    cpu_available: int = 0


class ResourceManager:
    """Manages and tracks resource usage across cluster nodes."""

    def __init__(self) -> None:
        """Initialize the resource manager."""
        self._nodes: dict[str, Node] = {}
        self._resource_usage: dict[str, ResourceUsage] = {}

    def add_node(self, node: Node) -> None:
        """Add a node to track."""
        self._nodes[node.id] = node
        self._resource_usage[node.id] = ResourceUsage(
            gpu_available=node.gpu_count,
            memory_available_gb=float(node.memory_gb),
            cpu_available=node.cpu_cores,
        )

    def remove_node(self, node_id: str) -> None:
        """Remove a node from tracking."""
        self._nodes.pop(node_id, None)
        self._resource_usage.pop(node_id, None)

    def get_available_nodes(self, gpu_required: int = 0, memory_required_gb: float = 0.0) -> List[str]:
        """Get nodes that have sufficient resources available."""
        available_nodes = []
        
        for node_id, usage in self._resource_usage.items():
            if (
                usage.gpu_available >= gpu_required
                and usage.memory_available_gb >= memory_required_gb
            ):
                available_nodes.append(node_id)
        
        return available_nodes

    def allocate_resources(
        self,
        node_id: str,
        gpu_count: int = 0,
        memory_gb: float = 0.0,
        cpu_cores: int = 0,
    ) -> bool:
        """Allocate resources on a specific node."""
        if node_id not in self._resource_usage:
            return False
        
        usage = self._resource_usage[node_id]
        
        # Check if resources are available
        if (
            usage.gpu_available < gpu_count
            or usage.memory_available_gb < memory_gb
            or usage.cpu_available < cpu_cores
        ):
            return False
        
        # Allocate resources
        usage.gpu_used += gpu_count
        usage.gpu_available -= gpu_count
        usage.memory_used_gb += memory_gb
        usage.memory_available_gb -= memory_gb
        usage.cpu_used += cpu_cores
        usage.cpu_available -= cpu_cores
        
        return True

    def release_resources(
        self,
        node_id: str,
        gpu_count: int = 0,
        memory_gb: float = 0.0,
        cpu_cores: int = 0,
    ) -> bool:
        """Release resources on a specific node."""
        if node_id not in self._resource_usage:
            return False
        
        usage = self._resource_usage[node_id]
        
        # Release resources
        usage.gpu_used = max(0, usage.gpu_used - gpu_count)
        usage.gpu_available += gpu_count
        usage.memory_used_gb = max(0, usage.memory_used_gb - memory_gb)
        usage.memory_available_gb += memory_gb
        usage.cpu_used = max(0, usage.cpu_used - cpu_cores)
        usage.cpu_available += cpu_cores
        
        return True

    def get_resource_usage(self, node_id: str) -> Optional[ResourceUsage]:
        """Get current resource usage for a node."""
        return self._resource_usage.get(node_id)

    def get_cluster_resources(self) -> Dict[str, ResourceUsage]:
        """Get resource usage for all nodes."""
        return self._resource_usage.copy()
