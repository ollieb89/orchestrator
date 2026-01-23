"""Command-line interface for Distributed Grid."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional, Dict, Any

import click
from pydantic import ValidationError
import yaml
from rich.console import Console
from rich.table import Table

from distributed_grid.core import GridOrchestrator
from distributed_grid.config import ClusterConfig, Settings
from distributed_grid.utils.logging import setup_logging
from distributed_grid.provisioning import GridProvisioner
from distributed_grid.cluster import RayClusterManager
from distributed_grid.core.executor import GridExecutor
from distributed_grid.core.ssh_manager import SSHManager
from distributed_grid.orchestration.resource_sharing_orchestrator import ResourceSharingOrchestrator
from distributed_grid.orchestration.resource_sharing_manager import ResourceType, AllocationPriority
from distributed_grid.orchestration.offloading_detector import OffloadingDetector
from distributed_grid.orchestration.offloading_executor import OffloadingExecutor

console = Console()


@click.group()
def cli():
    """Distributed GPU cluster orchestration tool."""
    pass


@click.group()
def boost():
    """Resource boost management commands."""
    pass


@cli.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(path_type=Path),
    default=Path("config/my-cluster.yaml"),
    help="Path to cluster configuration file",
)
def init(config: Path) -> None:
    """Initialize a new cluster configuration."""
    setup_logging()
    
    if config.exists():
        if not click.confirm(f"Configuration file {config} already exists. Overwrite?"):
            console.print("[yellow]Initialization cancelled.[/yellow]")
            return
    
    config.parent.mkdir(parents=True, exist_ok=True)
    
    sample_config = {
        "name": "my-cluster",
        "nodes": [
            {
                "name": "node-01",
                "host": "192.168.1.100",
                "port": 22,
                "user": "username",
                "gpu_count": 4,
                "memory_gb": 64,
                "tags": ["gpu", "cuda"],
            }
        ],
        "execution": {
            "default_nodes": 1,
            "default_gpus_per_node": 1,
            "timeout_seconds": 3600,
            "retry_attempts": 3,
            "working_directory": "/tmp/grid",
        },
        "logging": {
            "level": "INFO",
            "format": "json",
        },
    }
    
    with open(config, "w") as f:
        yaml.dump(sample_config, f, default_flow_style=False, indent=2)
    
    console.print(f"[green]✓[/green] Configuration initialized at {config}")


@cli.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    default=Path("config/my-cluster-enhanced.yaml"),
    help="Path to cluster configuration file",
)
def status(config: Path) -> None:
    """Show cluster and resource boost status."""
    setup_logging()
    
    async def _status():
        try:
            import ray
            from rich.panel import Panel
            
            cluster_config = ClusterConfig.from_yaml(config)
            
            # Try to connect to Ray
            try:
                ray.init(address="auto", ignore_reinit_error=True)
                nodes = ray.nodes()
                alive_nodes = [n for n in nodes if n.get("Alive", False)]
                
                console.print(Panel(
                    f"[green]Cluster Online[/green]\n"
                    f"Nodes: {len(alive_nodes)}/{len(nodes)} alive\n"
                    f"Head: {cluster_config.nodes[0].host}",
                    title="Cluster Status"
                ))
                
            except Exception:
                console.print(Panel(
                    "[red]Cluster Offline[/red]\n"
                    "Run: grid cluster start",
                    title="Cluster Status"
                ))
                return
            
            # Show boost status summary
            try:
                from distributed_grid.orchestration.resource_boost_manager import ResourceBoostManager
                from distributed_grid.monitoring.resource_metrics import ResourceMetricsCollector
                from distributed_grid.orchestration.resource_sharing_manager import ResourceSharingManager
                
                metrics = ResourceMetricsCollector(cluster_config)
                await metrics.start()
                
                sharing_mgr = ResourceSharingManager(cluster_config, metrics)
                boost_mgr = ResourceBoostManager(cluster_config, metrics, sharing_mgr)
                await boost_mgr.initialize()
                
                boost_status = await boost_mgr.get_boost_status()
                active = boost_status.get('total_active_boosts', 0)
                
                if active > 0:
                    console.print(f"\n[cyan]Active Resource Boosts: {active}[/cyan]")
                    console.print("Run: grid boost status (for details)")
                else:
                    console.print("\n[dim]No active resource boosts[/dim]")
                    
            except Exception as e:
                console.print(f"\n[yellow]Could not fetch boost status: {e}[/yellow]")
                
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
        finally:
            if ray.is_initialized():
                ray.shutdown()
    
    asyncio.run(_status())


@cli.command()
@click.argument(
    "config_path",
    type=click.Path(exists=True, path_type=Path),
)
def config(config_path: Path) -> None:
    """Validate a cluster configuration file."""
    setup_logging()
    
    try:
        cluster_config = ClusterConfig.from_yaml(config_path)
        console.print(f"[green]✓[/green] Configuration is valid")
        console.print(f"  Cluster: {cluster_config.name}")
        console.print(f"  Nodes: {len(cluster_config.nodes)}")
        
        # Display node details
        table = Table(title="Node Configuration")
        table.add_column("Name", style="cyan")
        table.add_column("Host", style="magenta")
        table.add_column("GPUs", justify="right")
        table.add_column("Memory", justify="right")
        
        for node in cluster_config.nodes:
            table.add_row(
                node.name,
                f"{node.host}:{node.port}",
                str(node.gpu_count),
                f"{node.memory_gb}GB"
            )
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]✗[/red] Configuration validation failed: {e}")
        raise click.ClickException(str(e))


@cli.group()
def cluster():
    """Ray cluster management."""
    pass


@cluster.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(path_type=Path),
    default=Path("config/my-cluster.yaml"),
    help="Path to cluster configuration file",
)
@click.option(
    "--ray-version",
    default="latest",
    help="Ray version to install",
)
@click.option(
    "--additional-packages",
    multiple=True,
    help="Additional packages to install with Ray",
)
@click.pass_context
def install(ctx, config, ray_version, additional_packages):
    """Install Ray on all cluster nodes."""
    setup_logging()
    
    async def _install():
        try:
            cluster_config = ClusterConfig.from_yaml(config)
            manager = RayClusterManager(cluster_config)
            
            await manager.install_ray(
                ray_version=ray_version,
                additional_packages=list(additional_packages) if additional_packages else ["torch", "numpy"]
            )
            
        except Exception as e:
            console.print(f"[red]Installation failed: {e}[/red]")
            raise click.ClickException(str(e))
    
    asyncio.run(_install())


@cluster.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(path_type=Path),
    default=Path("config/my-cluster.yaml"),
    help="Path to cluster configuration file",
)
@click.option(
    "--port",
    type=int,
    default=6399,
    help="Ray head node port",
)
@click.option(
    "--dashboard-port",
    type=int,
    default=8265,
    help="Ray dashboard port",
)
@click.pass_context
def start(ctx, config, port, dashboard_port):
    """Start the Ray cluster."""
    setup_logging()
    
    async def _start():
        try:
            cluster_config = ClusterConfig.from_yaml(config)
            manager = RayClusterManager(cluster_config)
            
            await manager.start_cluster(port=port, dashboard_port=dashboard_port)
            
        except Exception as e:
            console.print(f"[red]Failed to start cluster: {e}[/red]")
            raise click.ClickException(str(e))
    
    asyncio.run(_start())


@cluster.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(path_type=Path),
    default=Path("config/my-cluster.yaml"),
    help="Path to cluster configuration file",
)
@click.pass_context
def stop(ctx, config):
    """Stop the Ray cluster."""
    setup_logging()
    
    async def _stop():
        try:
            cluster_config = ClusterConfig.from_yaml(config)
            manager = RayClusterManager(cluster_config)
            
            await manager.stop_cluster()
            
        except Exception as e:
            console.print(f"[red]Failed to stop cluster: {e}[/red]")
            raise click.ClickException(str(e))
    
    asyncio.run(_stop())


@cluster.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(path_type=Path),
    default=Path("config/my-cluster.yaml"),
    help="Path to cluster configuration file",
)
@click.pass_context
def status(ctx, config):
    """Check Ray cluster status."""
    setup_logging()
    
    async def _status():
        try:
            cluster_config = ClusterConfig.from_yaml(config)
            manager = RayClusterManager(cluster_config)
            
            await manager.get_cluster_status()
            
        except Exception as e:
            console.print(f"[red]Failed to get status: {e}[/red]")
            raise click.ClickException(str(e))
    
    asyncio.run(_status())


@cli.command()
def version() -> None:
    """Show version information."""
    from distributed_grid import __version__
    console.print(f"Distributed Grid v{__version__}")


@boost.command()
@click.argument("target_node", type=str)
@click.argument("resource_type", type=click.Choice(["cpu", "gpu", "memory"], case_sensitive=False))
@click.argument("amount", type=float)
@click.option("--priority", type=click.Choice(["low", "normal", "high", "critical"], case_sensitive=False), 
              default="normal", help="Request priority")
@click.option("--duration", type=float, help="Duration in seconds (default: 1 hour)")
@click.option("--source", type=str, help="Preferred source node")
@click.option("--config", "-c", type=click.Path(exists=True, path_type=Path), 
              default=Path("config/my-cluster-enhanced.yaml"))
def request(target_node: str, resource_type: str, amount: float, priority: str, 
           duration: float | None, source: str | None, config: Path) -> None:
    """Request a resource boost for a node.
    
    Examples:
        grid boost request gpu-master cpu 2.0 --priority high
        grid boost request gpu-master gpu 1 --duration 1800
        grid boost request gpu-master memory 4.0 --source gpu2
    """
    setup_logging()
    
    async def _request():
        try:
            import ray
            from distributed_grid.orchestration.resource_boost_manager import (
                ResourceBoostManager, 
                ResourceBoostRequest,
                ResourceType,
                AllocationPriority
            )
            from distributed_grid.monitoring.resource_metrics import ResourceMetricsCollector
            from distributed_grid.orchestration.resource_sharing_manager import ResourceSharingManager
            
            # Initialize Ray
            if not ray.is_initialized():
                ray.init(address="auto")
            
            cluster_config = ClusterConfig.from_yaml(config)
            
            # Initialize components
            metrics_collector = ResourceMetricsCollector(cluster_config)
            await metrics_collector.start()
            
            resource_sharing_manager = ResourceSharingManager(
                cluster_config=cluster_config,
                metrics_collector=metrics_collector
            )
            await resource_sharing_manager.start()
            
            boost_manager = ResourceBoostManager(
                cluster_config=cluster_config,
                metrics_collector=metrics_collector,
                resource_sharing_manager=resource_sharing_manager
            )
            await boost_manager.initialize()
            
            # Create the request
            request = ResourceBoostRequest(
                target_node=target_node,
                resource_type=ResourceType[resource_type.upper()],
                amount=amount,
                priority=AllocationPriority[priority.upper()],
                duration_seconds=duration,
                preferred_source=source
            )
            
            # Request the boost
            boost_id = await boost_manager.request_boost(request)
            
            if boost_id:
                console.print(f"[green]✓[/green] Resource boost requested successfully")
                console.print(f"Boost ID: [bold]{boost_id}[/bold]")
                console.print(f"Target: {target_node}")
                console.print(f"Resource: {resource_type.upper()} x{amount}")
                console.print(f"Priority: {priority}")
                if duration:
                    console.print(f"Duration: {duration} seconds")
                if source:
                    console.print(f"Source: {source}")
            else:
                console.print("[red]✗[/red] Failed to request resource boost")
                console.print("Possible reasons:")
                console.print("• No nodes have sufficient available resources")
                console.print("• Target node not found in cluster")
                console.print("• Resource sharing not enabled")
                
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            import traceback
            console.print(traceback.format_exc())
    
    asyncio.run(_request())


@boost.command()
@click.argument("boost_id", type=str)
@click.option("--config", "-c", type=click.Path(exists=True, path_type=Path), 
              default=Path("config/my-cluster-enhanced.yaml"))
def release(boost_id: str, config: Path) -> None:
    """Release an active resource boost.
    
    Example:
        grid boost release <boost-id>
    """
    setup_logging()
    
    async def _release():
        try:
            import ray
            from distributed_grid.orchestration.resource_boost_manager import ResourceBoostManager
            from distributed_grid.monitoring.resource_metrics import ResourceMetricsCollector
            from distributed_grid.orchestration.resource_sharing_manager import ResourceSharingManager
            
            # Initialize Ray
            if not ray.is_initialized():
                ray.init(address="auto")
            
            cluster_config = ClusterConfig.from_yaml(config)
            
            # Initialize components
            metrics_collector = ResourceMetricsCollector(cluster_config)
            await metrics_collector.start()
            
            resource_sharing_manager = ResourceSharingManager(
                cluster_config=cluster_config,
                metrics_collector=metrics_collector
            )
            
            boost_manager = ResourceBoostManager(
                cluster_config=cluster_config,
                metrics_collector=metrics_collector,
                resource_sharing_manager=resource_sharing_manager
            )
            await boost_manager.initialize()
            
            # Release the boost
            success = await boost_manager.release_boost(boost_id)
            
            if success:
                console.print(f"[green]✓[/green] Resource boost released successfully")
                console.print(f"Boost ID: {boost_id}")
            else:
                console.print(f"[red]✗[/red] Failed to release boost {boost_id}")
                console.print("Boost not found or already released")
                
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
    
    asyncio.run(_release())


@boost.command()
@click.option("--node", type=str, help="Filter by target node")
@click.option("--config", "-c", type=click.Path(exists=True, path_type=Path), 
              default=Path("config/my-cluster-enhanced.yaml"))
def status(node: str | None, config: Path) -> None:
    """Show resource boost status.
    
    Examples:
        grid boost status
        grid boost status --node gpu-master
    """
    setup_logging()
    
    async def _status():
        try:
            import ray
            from distributed_grid.orchestration.resource_boost_manager import ResourceBoostManager
            from distributed_grid.monitoring.resource_metrics import ResourceMetricsCollector
            from distributed_grid.orchestration.resource_sharing_manager import ResourceSharingManager
            from rich.table import Table
            
            # Initialize Ray
            if not ray.is_initialized():
                ray.init(address="auto")
            
            cluster_config = ClusterConfig.from_yaml(config)
            
            # Initialize components
            metrics_collector = ResourceMetricsCollector(cluster_config)
            await metrics_collector.start()
            
            resource_sharing_manager = ResourceSharingManager(
                cluster_config=cluster_config,
                metrics_collector=metrics_collector
            )
            await resource_sharing_manager.start()
            
            boost_manager = ResourceBoostManager(
                cluster_config=cluster_config,
                metrics_collector=metrics_collector,
                resource_sharing_manager=resource_sharing_manager
            )
            await boost_manager.initialize()
            
            # Get status
            boost_status = await boost_manager.get_boost_status()
            active_boosts = await boost_manager.get_active_boosts(target_node=node)
            
            console.print("\n[bold]Resource Boost Status[/bold]\n")
            
            # Summary
            console.print(f"Total Active Boosts: {boost_status['total_active_boosts']}")
            
            if boost_status['boosted_resources']:
                console.print("\n[bold]Boosted Resources by Type:[/bold]")
                for rtype, amount in boost_status['boosted_resources'].items():
                    console.print(f"  {rtype}: {amount}")
            
            # Active boosts table
            if active_boosts:
                console.print("\n[bold]Active Boosts:[/bold]")
                table = Table()
                table.add_column("Boost ID", style="cyan")
                table.add_column("Source", justify="center")
                table.add_column("Target", justify="center")
                table.add_column("Resource", justify="center")
                table.add_column("Amount", justify="right")
                table.add_column("Allocated", justify="center")
                table.add_column("Expires", justify="center")
                
                for boost in active_boosts:
                    expires = boost.expires_at.strftime("%Y-%m-%d %H:%M:%S") if boost.expires_at else "Never"
                    table.add_row(
                        boost.boost_id[:8] + "...",
                        boost.source_node,
                        boost.target_node,
                        boost.resource_type.value,
                        str(boost.amount),
                        boost.allocated_at.strftime("%H:%M:%S"),
                        expires
                    )
                
                console.print(table)
            else:
                console.print("\n[dim]No active boosts[/dim]")
                
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
    
    asyncio.run(_status())


def main() -> None:
    """Entry point for the CLI."""
    cli.add_command(boost)
    cli()


if __name__ == "__main__":
    main()
