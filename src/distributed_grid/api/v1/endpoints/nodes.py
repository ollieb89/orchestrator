"""Node management endpoints."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, status

from distributed_grid.schemas.node import Node, NodeCreate, NodeUpdate, NodeStatus
from distributed_grid.services.node_service import NodeService

router = APIRouter()
node_service = NodeService()


@router.get("/", response_model=List[Node])
async def list_nodes(cluster_id: str = None) -> List[Node]:
    """List all nodes, optionally filtered by cluster."""
    return await node_service.list_nodes(cluster_id)


@router.post("/", response_model=Node, status_code=status.HTTP_201_CREATED)
async def create_node(node_data: NodeCreate) -> Node:
    """Create a new node."""
    try:
        return await node_service.create_node(node_data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{node_id}", response_model=Node)
async def get_node(node_id: str) -> Node:
    """Get a specific node by ID."""
    node = await node_service.get_node(node_id)
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )
    return node


@router.put("/{node_id}", response_model=Node)
async def update_node(node_id: str, node_data: NodeUpdate) -> Node:
    """Update a node."""
    try:
        node = await node_service.update_node(node_id, node_data)
        if not node:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Node not found",
            )
        return node
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete("/{node_id}")
async def delete_node(node_id: str) -> None:
    """Delete a node."""
    success = await node_service.delete_node(node_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )


@router.post("/{node_id}/status", response_model=NodeStatus)
async def check_node_status(node_id: str) -> NodeStatus:
    """Check the status of a node."""
    try:
        return await node_service.check_status(node_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
