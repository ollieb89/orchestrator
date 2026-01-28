from __future__ import annotations

from typing import Optional

from distributed_grid.monitoring.monitor_facade import MonitorFacade
from distributed_grid.orchestration.auto_offload_state import AutoOffloadState
from distributed_grid.orchestration.offloading_detector import OffloadingDetector
from distributed_grid.orchestration.offloading_executor import OffloadingExecutor
from distributed_grid.orchestration.policy_engine import PolicyEngine
from distributed_grid.core.ssh_manager import SSHManager


class OffloadingService:
    def __init__(self, cluster_config, ssh_manager=None) -> None:
        self.cluster_config = cluster_config
        self.ssh_manager = ssh_manager
        self.monitor = MonitorFacade(cluster_config, ssh_manager=ssh_manager)
        self.policy = PolicyEngine(0.8, 0.7, 0.9, 5)
        self.state = AutoOffloadState()
        self._owned_ssh_manager = False
        self._executor: Optional[OffloadingExecutor] = None

    async def _ensure_ssh_manager(self) -> SSHManager:
        if self.ssh_manager is None:
            self.ssh_manager = SSHManager(self.cluster_config.nodes)
            await self.ssh_manager.initialize()
            self._owned_ssh_manager = True
        return self.ssh_manager

    async def shutdown(self) -> None:
        if self._owned_ssh_manager and self.ssh_manager:
            await self.ssh_manager.close_all()
            self._owned_ssh_manager = False

    async def scan(self, target_node: Optional[str] = None):
        ssh_manager = await self._ensure_ssh_manager()
        detector = OffloadingDetector(ssh_manager, self.cluster_config)
        try:
            return await detector.detect_offloading_candidates(target_node=target_node)
        finally:
            await self.shutdown()

    async def execute(
        self,
        pid: int,
        target_node: Optional[str] = None,
        capture_state: bool = True,
        runtime_env: Optional[dict] = None,
        ray_dashboard: str = "http://localhost:8265",
    ) -> str:
        ssh_manager = await self._ensure_ssh_manager()
        detector = OffloadingDetector(ssh_manager, self.cluster_config)
        recommendations = await detector.detect_offloading_candidates(target_node=target_node)

        target_rec = None
        for rec in recommendations:
            if rec.process.pid == pid:
                if target_node is None or rec.target_node == target_node:
                    target_rec = rec
                    break

        if not target_rec:
            raise ValueError(f"Process {pid} not found or not offloadable")

        self._executor = OffloadingExecutor(ssh_manager, self.cluster_config, ray_dashboard)
        await self._executor.initialize()
        return await self._executor.execute_offloading(
            target_rec,
            capture_state=capture_state,
            runtime_env=runtime_env,
        )

    def _is_worker_target(self, node_name: str) -> bool:
        return node_name != self.cluster_config.nodes[0].name

    def get_task_status(self, task_id: str):
        if not self._executor:
            return None
        return self._executor.get_task_status(task_id)

    def auto_enable(self, interval: int, thresholds: dict) -> None:
        self.state.enabled = True
        self.state.thresholds = thresholds
        self.state.save()

    async def status(self) -> dict:
        return {
            "enabled": self.state.enabled,
            "thresholds": self.state.thresholds,
            "active_offloads": self.state.active_offloads,
            "recent_events": [e.to_dict() for e in self.state.recent_events],
            "queue_depth": 0,
        }
