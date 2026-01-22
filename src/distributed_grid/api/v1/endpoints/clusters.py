"""Cluster management endpoints."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, status

from distributed_grid.schemas.cluster import Cluster, ClusterCreate, ClusterUpdate
from distributed_grid.services.cluster_service import ClusterService

router = APIRouter()
cluster_service = ClusterService()


@router.get("/", response_model=List[Cluster])
async def list_clusters() -> List[Cluster]:
    """List all clusters."""
    return await cluster_service.list_clusters()


@router.post("/", response_model=Cluster, status_code=status.HTTP_201_CREATED)
async def create_cluster(cluster_data: ClusterCreate) -> Cluster:
    """Create a new cluster."""
    try:
        return await cluster_service.create_cluster(cluster_data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{cluster_id}", response_model=Cluster)
async def get_cluster(cluster_id: str) -> Cluster:
    """Get a specific cluster by ID."""
    cluster = await cluster_service.get_cluster(cluster_id)
    if not cluster:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cluster not found",
        )
    return cluster


@router.put("/{cluster_id}", response_model=Cluster)
async def update_cluster(cluster_id: str, cluster_data: ClusterUpdate) -> Cluster:
    """Update a cluster."""
    try:
        cluster = await cluster_service.update_cluster(cluster_id, cluster_data)
        if not cluster:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cluster not found",
            )
        return cluster
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete("/{cluster_id}")
async def delete_cluster(cluster_id: str) -> None:
    """Delete a cluster."""
    success = await cluster_service.delete_cluster(cluster_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cluster not found",
        )
