"""SSH connection management for cluster nodes."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import paramiko
import structlog

from distributed_grid.config import NodeConfig

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class SSHCommandResult:
    stdout: str
    stderr: str
    exit_status: int


class SSHManager:
    """Manages SSH connections to cluster nodes."""

    def __init__(self, nodes: list[NodeConfig]) -> None:
        self._nodes_by_name: dict[str, NodeConfig] = {n.name: n for n in nodes}
        self._clients: Dict[str, paramiko.SSHClient] = {}
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Establish SSH connections to all configured nodes."""
        await asyncio.gather(*(self._ensure_connected(n.name) for n in self._nodes_by_name.values()))

    async def close_all(self) -> None:
        """Close all SSH connections."""
        async with self._lock:
            for name, client in list(self._clients.items()):
                try:
                    await asyncio.to_thread(client.close)
                except Exception:
                    logger.warning("Failed closing SSH connection", node=name)
            self._clients.clear()

    def list_nodes(self) -> list[NodeConfig]:
        """Return configured nodes."""
        return list(self._nodes_by_name.values())

    async def run_command(
        self,
        node_name: str,
        command: str,
        timeout: int = 30,
    ) -> SSHCommandResult:
        """Run a command on a node."""
        await self._ensure_connected(node_name)

        client = self._clients[node_name]

        def _exec() -> SSHCommandResult:
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            exit_status = stdout.channel.recv_exit_status()
            return SSHCommandResult(
                stdout=stdout.read().decode(errors="replace").strip(),
                stderr=stderr.read().decode(errors="replace").strip(),
                exit_status=exit_status,
            )

        return await asyncio.to_thread(_exec)

    async def _ensure_connected(self, node_name: str) -> None:
        if node_name not in self._nodes_by_name:
            raise KeyError(f"Unknown node: {node_name}")

        async with self._lock:
            if node_name in self._clients:
                return

            node = self._nodes_by_name[node_name]

            def _connect() -> paramiko.SSHClient:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                client.connect(
                    hostname=node.host,
                    port=node.port,
                    username=node.user,
                    key_filename=str(node.ssh_key_path) if node.ssh_key_path else None,
                    timeout=10,
                )
                return client

            client = await asyncio.to_thread(_connect)
            self._clients[node_name] = client
            logger.info("SSH connected", node=node_name, host=node.host)
