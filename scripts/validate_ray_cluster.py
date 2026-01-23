#!/usr/bin/env python3
"""Validate Ray cluster health and heartbeat configuration."""

import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path

import structlog
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from distributed_grid.config import ClusterConfig
from distributed_grid.cluster import RayClusterManager

logger = structlog.get_logger(__name__)
console = Console()


async def check_cluster_health(config_path: str):
    """Check the health of the Ray cluster."""
    console.print("[blue]Checking Ray cluster health...[/blue]")
    
    # Load configuration
    cluster_config = ClusterConfig.from_yaml(config_path)
    manager = RayClusterManager(cluster_config)
    
    # Get cluster status
    status = await manager.get_cluster_status()
    
    # Create status table
    table = Table(title="Ray Cluster Node Status")
    table.add_column("Node", style="cyan", no_wrap=True)
    table.add_column("Status", style="green")
    table.add_column("Details", style="white")
    
    all_healthy = True
    
    for node_name, node_status in status.items():
        if node_status["exit_code"] == 0:
            # Parse ray status output
            output = node_status.get("stdout", "")
            if "is running" in output.lower():
                status_text = "[green]✓ Running[/green]"
                details = "Active"
            else:
                status_text = "[yellow]⚠ Unknown[/yellow]"
                details = output.strip()[:50]
                all_healthy = False
        else:
            status_text = "[red]✗ Error[/red]"
            details = node_status.get("stderr", "Unknown error")[:50]
            all_healthy = False
        
        table.add_row(node_name, status_text, details)
    
    console.print(table)
    
    # Check dashboard
    console.print("\n[blue]Checking Ray Dashboard...[/blue]")
    head_node = cluster_config.nodes[0]
    dashboard_cmd = f"curl -s http://localhost:{cluster_config.ray.dashboard_port} | head -20"
    
    try:
        result = await manager.ssh_manager.run_command(
            head_node.name, 
            dashboard_cmd, 
            timeout=10
        )
        
        if result.exit_status == 0 and "ray" in result.stdout.lower():
            console.print("[green]✓ Dashboard is accessible[/green]")
        else:
            console.print("[red]✗ Dashboard not responding[/red]")
            all_healthy = False
    except Exception as e:
        console.print(f"[red]✗ Failed to check dashboard: {e}[/red]")
        all_healthy = False
    
    # Summary
    if all_healthy:
        console.print(
            Panel(
                "[green]✓ Cluster is healthy![/green]\n"
                "All nodes are running and the dashboard is accessible.",
                title="Health Check Result",
                border_style="green"
            )
        )
    else:
        console.print(
            Panel(
                "[red]✗ Cluster has issues[/red]\n"
                "Some nodes are not responding or the dashboard is inaccessible.\n"
                "Check the logs above for details.",
                title="Health Check Result",
                border_style="red"
            )
        )
    
    return all_healthy


async def monitor_heartbeats(config_path: str, duration: int = 60):
    """Monitor cluster heartbeats for a specified duration."""
    console.print(f"[blue]Monitoring heartbeats for {duration} seconds...[/blue]")
    
    cluster_config = ClusterConfig.from_yaml(config_path)
    manager = RayClusterManager(cluster_config)
    
    start_time = time.time()
    check_interval = 10  # Check every 10 seconds
    
    while time.time() - start_time < duration:
        console.print(f"\n[cyan]Check at {datetime.now().strftime('%H:%M:%S')}[/cyan]")
        
        # Check GCS health
        head_node = cluster_config.nodes[0]
        gcs_check_cmd = (
            f"ps aux | grep 'ray.gcs_server' | grep -v grep || "
            f"echo 'GCS not running'"
        )
        
        try:
            result = await manager.ssh_manager.run_command(
                head_node.name,
                gcs_check_cmd,
                timeout=5
            )
            
            if "ray.gcs_server" in result.stdout:
                console.print("[green]✓ GCS server is running[/green]")
            else:
                console.print("[red]✗ GCS server not found[/red]")
        except Exception as e:
            console.print(f"[red]✗ Failed to check GCS: {e}[/red]")
        
        # Check node registration
        status = await manager.get_cluster_status()
        running_nodes = sum(
            1 for s in status.values() 
            if s["exit_code"] == 0 and "is running" in s.get("stdout", "").lower()
        )
        
        console.print(f"[green]✓ {running_nodes}/{len(cluster_config.nodes)} nodes active[/green]")
        
        if time.time() - start_time < duration:
            await asyncio.sleep(check_interval)
    
    console.print("\n[blue]Monitoring complete.[/blue]")


async def main():
    """Main validation script."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Validate Ray cluster health")
    parser.add_argument(
        "-c", "--config",
        default="config/my-cluster.yaml",
        help="Path to cluster configuration"
    )
    parser.add_argument(
        "--monitor",
        type=int,
        metavar="SECONDS",
        help="Monitor heartbeats for specified duration"
    )
    
    args = parser.parse_args()
    
    # Health check
    is_healthy = await check_cluster_health(args.config)
    
    # Optional monitoring
    if args.monitor:
        await monitor_heartbeats(args.config, args.monitor)
    
    # Exit with appropriate code
    sys.exit(0 if is_healthy else 1)


if __name__ == "__main__":
    asyncio.run(main())
