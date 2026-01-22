"""SSH connection management for cluster nodes."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
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
        self._ssh_config = self._load_ssh_config()

    @staticmethod
    def _load_ssh_config() -> Optional[paramiko.SSHConfig]:
        cfg_path = Path.home() / ".ssh" / "config"
        if not cfg_path.exists():
            return None
        try:
            cfg = paramiko.SSHConfig()
            cfg.parse(cfg_path.open())
            return cfg
        except Exception:
            return None

    def _lookup_ssh_config(self, host_alias: str) -> Dict[str, object]:
        if not self._ssh_config:
            return {}
        try:
            return self._ssh_config.lookup(host_alias) or {}
        except Exception:
            return {}

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

                # Base values from config
                base_hostname = node.host
                base_port = node.port
                base_username = node.user
                base_key_filename = str(node.ssh_key_path) if node.ssh_key_path else None

                # Values from ~/.ssh/config (match `ssh <alias>` behavior)
                ssh_cfg = self._lookup_ssh_config(node.host)
                cfg_hostname = ssh_cfg.get("hostname") or ssh_cfg.get("host")
                cfg_user = ssh_cfg.get("user")
                cfg_port = ssh_cfg.get("port")
                cfg_identity = ssh_cfg.get("identityfile")
                cfg_key_filename: Optional[str] = None
                if isinstance(cfg_identity, list) and cfg_identity:
                    cfg_key_filename = cfg_identity[0]
                elif isinstance(cfg_identity, str) and cfg_identity:
                    cfg_key_filename = cfg_identity

                # Try explicit config first; if it fails, retry using ssh config overrides.
                attempts = [
                    (base_hostname, base_port, base_username, base_key_filename),
                    (
                        str(cfg_hostname) if cfg_hostname else base_hostname,
                        int(cfg_port) if cfg_port else base_port,
                        str(cfg_user) if cfg_user else base_username,
                        cfg_key_filename or base_key_filename,
                    ),
                ]

                last_exc: Optional[Exception] = None
                for hostname, port, username, key_filename in attempts:
                    try:
                        client.load_system_host_keys()
                        client.connect(
                            hostname=hostname,
                            port=port,
                            username=username,
                            key_filename=key_filename,
                            timeout=10,
                            allow_agent=True,
                            look_for_keys=True,
                        )
                        return client
                    except Exception as e:
                        last_exc = e

                assert last_exc is not None
                raise last_exc
                return client

            client = await asyncio.to_thread(_connect)
            self._clients[node_name] = client
            logger.info("SSH connected", node=node_name, host=node.host)
