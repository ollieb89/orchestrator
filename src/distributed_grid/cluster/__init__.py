"""Ray cluster management functionality for Distributed Grid."""

from __future__ import annotations

import asyncio
import re
import socket
from pathlib import Path
from typing import Dict, List

import structlog
from rich.console import Console

from distributed_grid.config import ClusterConfig
from distributed_grid.core.ssh_manager import SSHManager, SSHCommandResult

logger = structlog.get_logger(__name__)
console = Console()


class RayClusterManager:
    """Manages Ray cluster operations."""
    
    def __init__(self, cluster_config: ClusterConfig) -> None:
        self.cluster_config = cluster_config
        self.ssh_manager = SSHManager(cluster_config.nodes)
        self.venv_path = "~/distributed_cluster_env"
        self.ray_bin = f"{self.venv_path}/bin/ray"
        self.python_bin = f"{self.venv_path}/bin/python"
        self.base_python = "python3.11"

    async def install_ray(
        self,
        ray_version: str = "latest",
        additional_packages: List[str] | None = None,
        python_executable: str = "python3.11"
    ) -> None:
        """Install Ray and dependencies on all nodes."""
        self.base_python = python_executable
        additional_packages = additional_packages or ["torch", "numpy"]
        
        console.print(f"[blue]Installing Ray on all nodes using {python_executable}...[/blue]")
        await self.ssh_manager.initialize()
        
        try:
            # Create virtual environment and install Ray on all nodes
            tasks = []
            for node in self.cluster_config.nodes:
                task = asyncio.create_task(
                    self._install_ray_on_node(node, ray_version, additional_packages)
                )
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for node, result in zip(self.cluster_config.nodes, results):
                if isinstance(result, Exception):
                    console.print(f"[red]✗[/red] Failed to install on {node.name}: {result}")
                else:
                    console.print(f"[green]✓[/green] Ray installed on {node.name}")
            
            console.print("[green]✓[/green] Ray installation complete")
            
        except Exception as e:
            console.print(f"[red]✗[/red] Installation failed: {e}")
            raise
        finally:
            await self.ssh_manager.close_all()
    
    async def _install_ray_on_node(
        self,
        node,
        ray_version: str,
        additional_packages: List[str]
    ) -> None:
        """Install Ray on a specific node."""
        logger.info("Installing Ray on node", node=node.name, python=self.base_python)
        
        # Create virtual environment using the specified base python
        setup_cmd = (
            f"{self.base_python} -m venv --clear {self.venv_path} && "
            f"{self.venv_path}/bin/pip install -U pip"
        )
        
        result = await self.ssh_manager.run_command(node.name, setup_cmd, timeout=120)
        if result.exit_status != 0:
            raise RuntimeError(f"Failed to create venv on {node.name}: {result.stderr}")
        
        # Install Ray with default extras
        ray_spec = f"'ray[default]'" if ray_version == "latest" else f"'ray[default]=={ray_version}'"
        packages_str = " ".join(additional_packages)
        
        install_cmd = f"{self.venv_path}/bin/pip install {ray_spec} {packages_str}"
        
        result = await self.ssh_manager.run_command(node.name, install_cmd, timeout=300)
        if result.exit_status != 0:
            raise RuntimeError(f"Failed to install Ray on {node.name}: {result.stderr}")
    
    async def start_cluster(self, port: int = 6399, dashboard_port: int = 8265) -> None:
        """Start the Ray cluster."""
        console.print("[blue]Starting Ray cluster...[/blue]")
        await self.ssh_manager.initialize()
        
        try:
            # Get head node (first node in config)
            head_node = self.cluster_config.nodes[0]
            worker_nodes = self.cluster_config.nodes[1:]
            
            # Start head node
            head_ip = await self._get_node_ip(head_node)
            try:
                await self._start_head_node(head_node, head_ip, port, dashboard_port)
                console.print(f"[green]Head node started at {head_ip}:{port}[/green]")
            except RuntimeError as e:
                # Handle case where head node is already running
                if "already running" in str(e).lower() or "ConnectionError" in str(e):
                    console.print(f"[yellow]Head node already running at {head_ip}:{port}. Proceeding with workers.[/yellow]")
                else:
                    raise

            redis_address = f"{head_ip}:{port}"
            
            # Wait for head node to be fully ready (give GCS time to initialize)
            console.print("[blue]Waiting for head node to be fully ready...[/blue]")
            await asyncio.sleep(30)
            
            # Verify GCS is ready before starting workers
            await self._wait_for_gcs_ready(head_ip, port)
            
            # Start worker nodes
            if worker_nodes:
                await self._start_worker_nodes(worker_nodes, redis_address)
            
            console.print(f"[green]✓[/green] Ray cluster is active!")
            console.print(f"Dashboard: http://localhost:{dashboard_port}")
            
        except Exception as e:
            console.print(f"[red]✗[/red] Failed to start cluster: {e}")
            raise
        finally:
            await self.ssh_manager.close_all()
    
    async def _start_head_node(self, head_node, head_ip: str, port: int, dashboard_port: int) -> None:
        """Start the Ray head node."""
        # Use fixed ports to make cluster networking predictable.
        node_manager_port = 10001
        object_manager_port = 10002
        ray_client_server_port = 10003
        min_worker_port = 11000
        max_worker_port = 11100
        
        # Ray system configuration for better heartbeat handling
        # Using both environment variables and command line flags for maximum compatibility
        ray_config = (
            "RAY_backend_log_level=debug "
            "RAY_heartbeat_timeout_ms=180000 "  # 180 seconds (3 minutes)
            "RAY_num_heartbeat_timeout_periods=20 "  # Allow 20 missed heartbeats
            "RAY_health_check_initial_delay_ms=30000 "  # 30 seconds initial delay
            "RAY_health_check_period_ms=30000 "  # Check every 30 seconds
            "RAY_health_check_timeout_ms=30000 "  # 30 seconds timeout for health checks
            "RAY_gcs_server_request_timeout_seconds_ms=300000 "  # 300 seconds GCS timeout
            "RAY_timeout_ms=300000 "  # General operation timeout
            "RAY_raylet_death_check_interval_ms=10000 "  # Check every 10 seconds
            "RAY_node_manager_timeout_ms=180000 "  # Node manager timeout
            "RAY_gcs_rpc_server_reconnect_timeout_s=300 "  # GCS RPC reconnect timeout
        )
        
        start_cmd = (
            f"{ray_config} {self.ray_bin} start --head "
            f"--port={port} "
            f"--node-ip-address={head_ip} "
            f"--node-manager-port={node_manager_port} "
            f"--object-manager-port={object_manager_port} "
            f"--ray-client-server-port={ray_client_server_port} "
            f"--min-worker-port={min_worker_port} "
            f"--max-worker-port={max_worker_port} "
            f"--dashboard-host=0.0.0.0 "
            f"--dashboard-port={dashboard_port} "
            f"--include-dashboard=true"
        )
        
        result = await self.ssh_manager.run_command(head_node.name, start_cmd, timeout=60)
        if result.exit_status != 0:
            raise RuntimeError(f"Failed to start head node: {result.stderr}")

    async def _get_node_ip(self, node) -> str:
        """Get a stable non-loopback LAN IP for a node."""
        # If the config host is already an IP, prefer that.
        if isinstance(getattr(node, "host", None), str) and re.match(r"^\d+\.\d+\.\d+\.\d+$", node.host):
            return node.host

        # Prefer first non-loopback from hostname -I.
        cmd = "hostname -I | tr ' ' '\n' | grep -vE '^(127\\.|::1$|$)' | head -n 1"
        result = await self.ssh_manager.run_command(node.name, cmd, timeout=10)
        if result.exit_status == 0 and result.stdout.strip():
            return result.stdout.strip()

        # Fallback: resolve configured hostname locally on the node.
        if isinstance(getattr(node, "host", None), str) and node.host:
            resolve_cmd = f"getent hosts {node.host} | awk '{{print $1}}' | head -n 1"
            result = await self.ssh_manager.run_command(node.name, resolve_cmd, timeout=10)
            if result.exit_status == 0 and result.stdout.strip():
                return result.stdout.strip()

        raise RuntimeError(f"Failed to determine node IP for {node.name}")
    
    async def _wait_for_gcs_ready(self, head_ip: str, port: int, max_retries: int = 15) -> None:
        """Wait for GCS server to be ready and responsive.
        
        Verifies that the GCS server is listening on its port before allowing
        workers to connect. This prevents "RPC error: Deadline Exceeded" failures.
        
        Args:
            head_ip: IP address of the head node
            port: GCS server port (Redis port)
            max_retries: Maximum number of connection attempts
            
        Raises:
            RuntimeError: If GCS doesn't become ready after max_retries
        """
        console.print(f"[blue]Waiting for GCS to be ready at {head_ip}:{port}...[/blue]")
        
        for attempt in range(1, max_retries + 1):
            try:
                # Try to connect to the GCS port
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)  # 2 second timeout per connection attempt
                result = sock.connect_ex((head_ip, port))
                sock.close()
                
                if result == 0:
                    console.print(f"[green]✓ GCS is ready at {head_ip}:{port}[/green]")
                    return
            except Exception as e:
                logger.debug("GCS connection attempt failed", attempt=attempt, error=str(e))
            
            if attempt < max_retries:
                console.print(f"[yellow]GCS not ready yet... (attempt {attempt}/{max_retries})[/yellow]")
                await asyncio.sleep(2)  # Wait 2 seconds before retry
        
        raise RuntimeError(
            f"GCS server not responding at {head_ip}:{port} after {max_retries} attempts. "
            f"Check that the head node is running and ports are accessible."
        )
    
    async def _start_worker_nodes(self, worker_nodes: List, redis_address: str) -> None:
        """Start Ray worker nodes."""
        tasks = []
        for node in worker_nodes:
            task = asyncio.create_task(
                self._start_worker_node(node, redis_address)
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for node, result in zip(worker_nodes, results):
            if isinstance(result, Exception):
                console.print(f"[red]✗[/red] Failed to start worker {node.name}: {result}")
            else:
                console.print(f"[green]✓[/green] Worker {node.name} connected")
    
    async def _start_worker_node(self, worker_node, redis_address: str) -> None:
        """Start a Ray worker node."""
        worker_ip = await self._get_node_ip(worker_node)
        
        # Use the same ports as head node for consistency
        node_manager_port = 10001
        object_manager_port = 10002
        ray_client_server_port = 10003
        min_worker_port = 11000
        max_worker_port = 11100
        
        # Ray system configuration for better heartbeat handling (same as head node)
        # Using both environment variables and command line flags for maximum compatibility
        ray_config = (
            "RAY_backend_log_level=debug "
            "RAY_heartbeat_timeout_ms=180000 "  # 180 seconds (3 minutes)
            "RAY_num_heartbeat_timeout_periods=20 "  # Allow 20 missed heartbeats
            "RAY_health_check_initial_delay_ms=30000 "  # 30 seconds initial delay
            "RAY_health_check_period_ms=30000 "  # Check every 30 seconds
            "RAY_health_check_timeout_ms=30000 "  # 30 seconds timeout for health checks
            "RAY_gcs_server_request_timeout_seconds_ms=300000 "  # 300 seconds GCS timeout
            "RAY_timeout_ms=300000 "  # General operation timeout
            "RAY_raylet_death_check_interval_ms=10000 "  # Check every 10 seconds
            "RAY_node_manager_timeout_ms=180000 "  # Node manager timeout
            "RAY_gcs_rpc_server_reconnect_timeout_s=300 "  # GCS RPC reconnect timeout
        )
        
        start_cmd = (
            f"{ray_config} {self.ray_bin} start "
            f"--address={redis_address} "
            f"--node-ip-address={worker_ip} "
            f"--node-manager-port={node_manager_port} "
            f"--object-manager-port={object_manager_port} "
            f"--ray-client-server-port={ray_client_server_port} "
            f"--min-worker-port={min_worker_port} "
            f"--max-worker-port={max_worker_port}"
        )
        
        result = await self.ssh_manager.run_command(worker_node.name, start_cmd, timeout=60)
        if result.exit_status != 0:
            raise RuntimeError(f"Failed to start worker {worker_node.name}: {result.stderr}")
    
    async def stop_cluster(self) -> None:
        """Stop the Ray cluster on all nodes."""
        console.print("[blue]Stopping Ray cluster...[/blue]")
        await self.ssh_manager.initialize()
        
        try:
            # Stop workers first
            worker_nodes = self.cluster_config.nodes[1:]
            if worker_nodes:
                await self._stop_worker_nodes(worker_nodes)
            
            # Stop head node
            head_node = self.cluster_config.nodes[0]
            await self._stop_head_node(head_node)
            
            console.print("[green]✓[/green] Ray cluster stopped")
            
        except Exception as e:
            console.print(f"[red]✗[/red] Failed to stop cluster: {e}")
            raise
        finally:
            await self.ssh_manager.close_all()
    
    async def _stop_worker_nodes(self, worker_nodes: List) -> None:
        """Stop Ray worker nodes."""
        tasks = []
        for node in worker_nodes:
            task = asyncio.create_task(self._stop_ray_on_node(node))
            tasks.append(task)
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _stop_head_node(self, head_node) -> None:
        """Stop Ray head node."""
        await self._stop_ray_on_node(head_node)
    
    async def _stop_ray_on_node(self, node) -> None:
        """Stop Ray on a specific node."""
        result = await self.ssh_manager.run_command(node.name, f"{self.ray_bin} stop", timeout=30)
        if result.exit_status != 0:
            logger.warning("Failed to stop Ray on node", node=node.name, stderr=result.stderr)
    
    async def get_cluster_status(self) -> Dict[str, Dict]:
        """Get Ray cluster status from all nodes."""
        console.print("[blue]Checking cluster status...[/blue]")
        await self.ssh_manager.initialize()
        
        status = {}
        
        try:
            for node in self.cluster_config.nodes:
                result = await self.ssh_manager.run_command(
                    node.name,
                    f"{self.ray_bin} status",
                    timeout=10
                )
                
                status[node.name] = {
                    "exit_code": result.exit_status,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "status": "running" if result.exit_status == 0 else "stopped"
                }
            
            # Display status
            for node_name, node_status in status.items():
                status_symbol = "[green]✓[/green]" if node_status["status"] == "running" else "[red]✗[/red]"
                console.print(f"{status_symbol} {node_name}: {node_status['status']}")
                
                if node_status["stdout"]:
                    # Parse and display key info from stdout
                    for line in node_status["stdout"].split("\n"):
                        if "node" in line.lower() or "ray" in line.lower():
                            console.print(f"  {line}")
            
            return status
            
        except Exception as e:
            console.print(f"[red]✗[/red] Failed to get status: {e}")
            raise
        finally:
            await self.ssh_manager.close_all()
