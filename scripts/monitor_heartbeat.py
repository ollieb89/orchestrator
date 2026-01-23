#!/usr/bin/env python3
"""
Ray Cluster Heartbeat Monitor
Monitors Ray cluster for heartbeat issues and provides automatic healing.
"""

import asyncio
import json
import sys
import time
from datetime import datetime, UTC
from pathlib import Path
from typing import Dict, List, Optional

import click
import structlog
from rich.console import Console
from rich.live import Live
from rich.table import Table

from distributed_grid.config import ClusterConfig
from distributed_grid.core.ssh_manager import SSHManager

logger = structlog.get_logger(__name__)
console = Console()


class HeartbeatMonitor:
    """Monitors Ray cluster heartbeat health."""
    
    def __init__(self, config_path: Path):
        self.config = ClusterConfig.from_yaml(config_path)
        self.ssh_manager = SSHManager(self.config.nodes)
        self.ray_bin = "~/distributed_cluster_env/bin/ray"
        self.alert_threshold = 3  # Number of consecutive failures before alert
        
    async def start_monitoring(
        self, 
        interval: int = 30, 
        duration: Optional[int] = None,
        auto_heal: bool = False
    ) -> None:
        """Start monitoring the cluster heartbeat health."""
        console.print("[blue]Starting Ray cluster heartbeat monitor...[/blue]")
        console.print(f"[green]Checking every {interval} seconds[/green]")
        
        start_time = time.time()
        failure_counts = {node.name: 0 for node in self.config.nodes}
        
        await self.ssh_manager.initialize()
        
        try:
            with Live(self._create_status_table(), refresh_per_second=1) as live:
                while True:
                    # Check current time
                    if duration and (time.time() - start_time) > duration:
                        console.print("[yellow]Monitoring duration completed[/yellow]")
                        break
                    
                    # Get cluster status
                    status = await self._check_cluster_health()
                    
                    # Update failure counts
                    for node_name, node_status in status.items():
                        if not node_status["healthy"]:
                            failure_counts[node_name] += 1
                        else:
                            failure_counts[node_name] = 0
                    
                    # Check for alerts
                    alerts = []
                    for node_name, count in failure_counts.items():
                        if count >= self.alert_threshold:
                            alerts.append(f"{node_name}: {count} consecutive failures")
                            
                            # Auto-heal if enabled
                            if auto_heal and count == self.alert_threshold:
                                console.print(f"[red]Attempting auto-heal for {node_name}[/red]")
                                await self._heal_node(node_name)
                    
                    # Update display
                    table = self._create_status_table(status, failure_counts, alerts)
                    live.update(table)
                    
                    # Sleep until next check
                    await asyncio.sleep(interval)
                    
        except KeyboardInterrupt:
            console.print("\n[yellow]Monitoring stopped by user[/yellow]")
        finally:
            await self.ssh_manager.close_all()
    
    async def _check_cluster_health(self) -> Dict[str, Dict]:
        """Check the health of all nodes in the cluster."""
        status = {}
        
        for node in self.config.nodes:
            try:
                # Check Ray status
                result = await self.ssh_manager.run_command(
                    node.name,
                    f"{self.ray_bin} status",
                    timeout=10
                )
                
                # Check for heartbeat errors in logs
                log_result = await self.ssh_manager.run_command(
                    node.name,
                    "tail -n 10 /tmp/ray/session_*/logs/raylet.err | grep -i 'heartbeat\\|death check' || echo 'No errors'",
                    timeout=5
                )
                
                # Determine health
                healthy = result.exit_status == 0 and "No errors" in log_result.stdout
                
                status[node.name] = {
                    "healthy": healthy,
                    "ray_status": "running" if result.exit_status == 0 else "stopped",
                    "last_check": datetime.now(UTC).isoformat(),
                    "errors": log_result.stdout if "No errors" not in log_result.stdout else None
                }
                
            except Exception as e:
                status[node.name] = {
                    "healthy": False,
                    "ray_status": "error",
                    "last_check": datetime.now(UTC).isoformat(),
                    "errors": str(e)
                }
        
        return status
    
    def _create_status_table(
        self, 
        status: Optional[Dict] = None,
        failures: Optional[Dict] = None,
        alerts: Optional[List[str]] = None
    ) -> Table:
        """Create a rich table showing cluster status."""
        table = Table(title="Ray Cluster Heartbeat Monitor")
        table.add_column("Node", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Ray", style="blue")
        table.add_column("Failures", style="yellow")
        table.add_column("Last Check", style="dim")
        
        if status:
            for node in self.config.nodes:
                node_status = status.get(node.name, {})
                failures_count = failures.get(node.name, 0) if failures else 0
                
                # Determine status icon
                if node_status.get("healthy", False):
                    status_icon = "[green]✓[/green]"
                elif failures_count >= self.alert_threshold:
                    status_icon = "[red]✗[/red]"
                else:
                    status_icon = "[yellow]⚠[/yellow]"
                
                table.add_row(
                    node.name,
                    status_icon,
                    node_status.get("ray_status", "unknown"),
                    str(failures_count),
                    node_status.get("last_check", "never")[:19] + "Z"
                )
        
        if alerts:
            table.add_row("", "", "", "", "")
            table.add_row("[red]ALERTS[/red]", "", "", "", "")
            for alert in alerts:
                table.add_row(f"[red]• {alert}[/red]", "", "", "", "")
        
        return table
    
    async def _heal_node(self, node_name: str) -> None:
        """Attempt to heal a node with heartbeat issues."""
        try:
            # Restart Ray on the node
            console.print(f"[yellow]Restarting Ray on {node_name}...[/yellow]")
            
            stop_cmd = f"{self.ray_bin} stop"
            await self.ssh_manager.run_command(node_name, stop_cmd, timeout=30)
            
            await asyncio.sleep(5)
            
            # Get the address from head node
            head_node = self.config.nodes[0]
            head_ip = await self._get_node_ip(head_node)
            
            if node_name == head_node.name:
                # Restart head node
                start_cmd = (
                    f"RAY_backend_log_level=debug "
                    f"RAY_heartbeat_timeout_ms=180000 "
                    f"RAY_num_heartbeat_timeout_periods=20 "
                    f"RAY_health_check_initial_delay_ms=30000 "
                    f"RAY_health_check_period_ms=30000 "
                    f"{self.ray_bin} start --head "
                    f"--port=6399 "
                    f"--node-ip-address={head_ip} "
                    f"--dashboard-host=0.0.0.0 "
                    f"--dashboard-port=8265"
                )
            else:
                # Restart worker node
                start_cmd = (
                    f"RAY_backend_log_level=debug "
                    f"RAY_heartbeat_timeout_ms=180000 "
                    f"RAY_num_heartbeat_timeout_periods=20 "
                    f"RAY_health_check_initial_delay_ms=30000 "
                    f"RAY_health_check_period_ms=30000 "
                    f"{self.ray_bin} start "
                    f"--address={head_ip}:6399"
                )
            
            result = await self.ssh_manager.run_command(node_name, start_cmd, timeout=30)
            
            if result.exit_status == 0:
                console.print(f"[green]✓ Successfully restarted Ray on {node_name}[/green]")
            else:
                console.print(f"[red]✗ Failed to restart Ray on {node_name}: {result.stderr}[/red]")
                
        except Exception as e:
            console.print(f"[red]✗ Auto-heal failed for {node_name}: {e}[/red]")
    
    async def _get_node_ip(self, node) -> str:
        """Get the IP address of a node."""
        cmd = "hostname -I | awk '{print $1}'"
        result = await self.ssh_manager.run_command(node.name, cmd, timeout=10)
        return result.stdout.strip() if result.exit_status == 0 else "127.0.0.1"


@click.command()
@click.option(
    "-c", "--config",
    type=click.Path(exists=True, path_type=Path),
    default="config/my-cluster.yaml",
    help="Cluster configuration file"
)
@click.option(
    "-i", "--interval",
    default=30,
    help="Monitoring interval in seconds"
)
@click.option(
    "-d", "--duration",
    type=int,
    help="Monitoring duration in seconds (optional)"
)
@click.option(
    "--auto-heal",
    is_flag=True,
    help="Enable automatic healing of failed nodes"
)
@click.option(
    "--alert-threshold",
    default=3,
    help="Number of consecutive failures before alert"
)
def main(config: Path, interval: int, duration: Optional[int], auto_heal: bool, alert_threshold: int) -> None:
    """Monitor Ray cluster heartbeat health."""
    monitor = HeartbeatMonitor(config)
    monitor.alert_threshold = alert_threshold
    
    asyncio.run(monitor.start_monitoring(interval, duration, auto_heal))


if __name__ == "__main__":
    main()
