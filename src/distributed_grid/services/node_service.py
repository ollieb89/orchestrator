"""Node service for managing node operations."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from distributed_grid.schemas.node import Node, NodeCreate, NodeStatus, NodeUpdate


class NodeService:
    """Service for managing nodes."""

    def __init__(self) -> None:
        """Initialize the node service."""
        # TODO: Replace with actual database/storage
        self._nodes: dict[str, Node] = {}

    async def list_nodes(self, cluster_id: Optional[str] = None) -> List[Node]:
        """List all nodes, optionally filtered by cluster."""
        nodes = list(self._nodes.values())
        if cluster_id:
            nodes = [n for n in nodes if n.cluster_id == cluster_id]
        return nodes

    async def get_node(self, node_id: str) -> Optional[Node]:
        """Get a node by ID."""
        return self._nodes.get(node_id)

    async def create_node(self, node_data: NodeCreate) -> Node:
        """Create a new node."""
        node_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        node = Node(
            id=node_id,
            created_at=now,
            updated_at=now,
            cluster_id=node_data.cluster_id,
            **node_data.dict(exclude={"cluster_id"}),
        )
        
        self._nodes[node_id] = node
        return node

    async def update_node(
        self,
        node_id: str,
        node_data: NodeUpdate,
    ) -> Optional[Node]:
        """Update a node."""
        node = self._nodes.get(node_id)
        if not node:
            return None
        
        update_data = node_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(node, field, value)
        
        node.updated_at = datetime.utcnow()
        return node

    async def delete_node(self, node_id: str) -> bool:
        """Delete a node."""
        if node_id in self._nodes:
            del self._nodes[node_id]
            return True
        return False

    async def check_status(self, node_id: str) -> NodeStatus:
        """Check the status of a node."""
        node = self._nodes.get(node_id)
        if not node:
            raise ValueError(f"Node {node_id} not found")
        
        # TODO: Implement actual health check
        # For now, return a mock status
        return NodeStatus(
            node_id=node_id,
            status="healthy",
            timestamp=datetime.utcnow(),
            gpu_utilization=0.5,
            memory_utilization=0.6,
            cpu_utilization=0.4,
        )
