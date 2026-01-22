"""Cluster service for managing cluster operations."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from distributed_grid.schemas.cluster import Cluster, ClusterCreate, ClusterUpdate


class ClusterService:
    """Service for managing clusters."""

    def __init__(self) -> None:
        """Initialize the cluster service."""
        # TODO: Replace with actual database/storage
        self._clusters: dict[str, Cluster] = {}

    async def list_clusters(self) -> List[Cluster]:
        """List all clusters."""
        return list(self._clusters.values())

    async def get_cluster(self, cluster_id: str) -> Optional[Cluster]:
        """Get a cluster by ID."""
        return self._clusters.get(cluster_id)

    async def create_cluster(self, cluster_data: ClusterCreate) -> Cluster:
        """Create a new cluster."""
        cluster_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        cluster = Cluster(
            id=cluster_id,
            created_at=now,
            updated_at=now,
            **cluster_data.dict(),
        )
        
        self._clusters[cluster_id] = cluster
        return cluster

    async def update_cluster(
        self,
        cluster_id: str,
        cluster_data: ClusterUpdate,
    ) -> Optional[Cluster]:
        """Update a cluster."""
        cluster = self._clusters.get(cluster_id)
        if not cluster:
            return None
        
        update_data = cluster_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(cluster, field, value)
        
        cluster.updated_at = datetime.utcnow()
        return cluster

    async def delete_cluster(self, cluster_id: str) -> bool:
        """Delete a cluster."""
        if cluster_id in self._clusters:
            del self._clusters[cluster_id]
            return True
        return False
