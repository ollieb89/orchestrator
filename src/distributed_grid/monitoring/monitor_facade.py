from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict

from distributed_grid.monitoring.resource_metrics import (
    ResourceMetricsCollector,
    ResourceSnapshot,
)


@dataclass
class ClusterSnapshot:
    head: ResourceSnapshot
    nodes: Dict[str, ResourceSnapshot]
    queue_depth: int
    timestamp: datetime


class MonitorFacade:
    def __init__(self, cluster_config, ssh_manager=None):
        self.cluster_config = cluster_config
        self.ssh_manager = ssh_manager
        self.metrics = ResourceMetricsCollector(
            cluster_config,
            ssh_manager=ssh_manager,
            head_only_mode=True,
        )

    def _normalize_snapshot(
        self,
        head_name: str,
        head_snapshot: ResourceSnapshot,
        queue_depth: int,
        node_snapshots: Dict[str, ResourceSnapshot],
    ) -> ClusterSnapshot:
        return ClusterSnapshot(
            head=head_snapshot,
            nodes=node_snapshots,
            queue_depth=queue_depth,
            timestamp=head_snapshot.timestamp,
        )
