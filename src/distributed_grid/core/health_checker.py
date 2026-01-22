"""Health checking for cluster nodes."""

from __future__ import annotations

import asyncio
from typing import List, Optional

import structlog
from pydantic import BaseModel, Field

from distributed_grid.config import NodeConfig
from distributed_grid.core.ssh_manager import SSHManager

logger = structlog.get_logger(__name__)


class NodeHealth(BaseModel):
    """Health information for a node."""

    is_online: bool
    load_average: Optional[List[float]] = None
    gpu_utilization: Optional[List[float]] = None
    error: Optional[str] = None


class HealthChecker:
    """Checks node health and resource utilization."""

    def __init__(self, ssh_manager: SSHManager, timeout: int = 10) -> None:
        self.ssh_manager = ssh_manager
        self.timeout = timeout

    async def check_all_nodes(self) -> list[NodeHealth]:
        """Check all nodes in the cluster."""
        nodes = self.ssh_manager.list_nodes()
        return await asyncio.gather(*(self.check_node(node) for node in nodes))

    async def check_node(self, node: NodeConfig) -> NodeHealth:
        """Check a single node."""
        try:
            result = await asyncio.wait_for(
                self.ssh_manager.run_command(
                    node.name,
                    "cat /proc/loadavg | awk '{print $1,$2,$3}'",
                    timeout=self.timeout,
                ),
                timeout=self.timeout + 2,
            )

            if result.exit_status != 0:
                return NodeHealth(is_online=False, error=result.stderr or "Non-zero exit")

            parts = result.stdout.strip().split()
            load_avg = [float(p) for p in parts[:3]] if len(parts) >= 3 else None

            gpu_util = await self._try_get_gpu_utilization(node)

            return NodeHealth(is_online=True, load_average=load_avg, gpu_utilization=gpu_util)
        except Exception as e:
            logger.warning("Health check failed", node=node.name, error=str(e))
            return NodeHealth(is_online=False, error=str(e))

    async def _try_get_gpu_utilization(self, node: NodeConfig) -> Optional[List[float]]:
        """Attempt to retrieve GPU utilization via nvidia-smi."""
        cmd = (
            "if command -v nvidia-smi >/dev/null 2>&1; then "
            "nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits; "
            "else echo ''; fi"
        )

        try:
            result = await self.ssh_manager.run_command(node.name, cmd, timeout=self.timeout)
            if result.exit_status != 0:
                return None

            lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
            if not lines:
                return None

            return [float(x) / 100.0 for x in lines]
        except Exception:
            return None
