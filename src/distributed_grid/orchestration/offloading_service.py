from __future__ import annotations

from distributed_grid.monitoring.monitor_facade import MonitorFacade
from distributed_grid.orchestration.auto_offload_state import AutoOffloadState
from distributed_grid.orchestration.policy_engine import PolicyEngine


class OffloadingService:
    def __init__(self, cluster_config, ssh_manager=None) -> None:
        self.cluster_config = cluster_config
        self.ssh_manager = ssh_manager
        self.monitor = MonitorFacade(cluster_config, ssh_manager=ssh_manager)
        self.policy = PolicyEngine(0.8, 0.7, 0.9, 5)
        self.state = AutoOffloadState()

    def _is_worker_target(self, node_name: str) -> bool:
        return node_name != self.cluster_config.nodes[0].name
