"""Command execution on cluster nodes."""

from __future__ import annotations

import asyncio
from typing import Dict

import structlog

from distributed_grid.config import ExecutionConfig, NodeConfig
from distributed_grid.core.ssh_manager import SSHManager

logger = structlog.get_logger(__name__)


class GridExecutor:
    """Executes commands on one or more nodes."""

    def __init__(self, ssh_manager: SSHManager, execution_config: ExecutionConfig) -> None:
        self.ssh_manager = ssh_manager
        self.execution_config = execution_config

    async def execute_on_nodes(self, command: str, nodes: list[NodeConfig]) -> Dict[str, str]:
        """Execute a command on multiple nodes concurrently."""
        results = await asyncio.gather(
            *(self._execute_on_node(command, node) for node in nodes),
            return_exceptions=True,
        )

        output: Dict[str, str] = {}
        for node, result in zip(nodes, results):
            if isinstance(result, Exception):
                output[node.name] = f"ERROR: {result}"
            else:
                output[node.name] = result
        return output

    async def _execute_on_node(self, command: str, node: NodeConfig) -> str:
        env_prefix = " ".join(
            f"{k}={self._shell_quote(v)}" for k, v in self.execution_config.environment.items()
        )

        mkdir_cmd = f"mkdir -p {self._shell_quote(self.execution_config.working_directory)}"
        await self.ssh_manager.run_command(node.name, mkdir_cmd, timeout=self.execution_config.timeout_seconds)

        cd_and_run = (
            f"cd {self._shell_quote(self.execution_config.working_directory)} && "
            f"{env_prefix + ' ' if env_prefix else ''}{command}"
        )

        logger.info("Executing command", node=node.name, command=command)
        result = await self.ssh_manager.run_command(
            node.name,
            cd_and_run,
            timeout=self.execution_config.timeout_seconds,
        )

        if result.stderr:
            logger.warning("Command stderr", node=node.name, stderr=result.stderr)

        return result.stdout

    @staticmethod
    def _shell_quote(value: str) -> str:
        # minimal quoting for paths / env values
        return "'" + value.replace("'", "'\\''") + "'"
