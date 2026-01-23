"""Command-line interface for Distributed Grid."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

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


@cli.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(path_type=Path),
    default=Path("config/my-cluster.yaml"),
    help="Path to cluster configuration file",
)
def start(config: Path) -> None:
    """Start the cluster orchestrator."""
    setup_logging()
    
    try:
        settings = Settings()
        cluster_config = ClusterConfig.from_yaml(config)
        
        console.print(f"[blue]Starting cluster {cluster_config.name}...[/blue]")
        
        # Initialize orchestrator
        orchestrator = GridOrchestrator(cluster_config)
        
        # Start the orchestrator
        asyncio.run(orchestrator.start())
        
    except Exception as e:
        console.print(f"[red]Failed to start cluster: {e}[/red]")
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
@click.option(
    "--config",
    "-c",
    type=click.Path(path_type=Path),
    default=Path("config/my-cluster.yaml"),
    help="Path to cluster configuration file",
)
@click.option(
    "--pip-packages",
    multiple=True,
    help="Additional pip packages to install",
)
@click.option(
    "--npm-packages",
    multiple=True,
    help="Additional npm packages to install",
)
@click.option(
    "--python-version",
    default="3.11",
    help="Python version to use for virtual environment",
)
@click.option(
    "--workspace-root",
    default="~/grid_workspace",
    help="Root directory for grid workspace",
)
@click.pass_context
def provision(ctx, config, pip_packages, npm_packages, python_version, workspace_root):
    """Provision cluster nodes with required environments."""
    setup_logging()
    
    async def _provision():
        try:
            cluster_config = ClusterConfig.from_yaml(config)
            provisioner = GridProvisioner(cluster_config)
            
            console.print(f"[blue]Provisioning {len(cluster_config.nodes)} nodes...[/blue]")
            
            await provisioner.provision_all(
                pip_packages=list(pip_packages) if pip_packages else None,
                npm_packages=list(npm_packages) if npm_packages else None,
                python_version=python_version,
                workspace_root=workspace_root
            )
            
        except Exception as e:
            console.print(f"[red]Provisioning failed: {e}[/red]")
            raise click.ClickException(str(e))
    
    asyncio.run(_provision())


@cli.command()
@click.argument(
    "command",
    type=str,
    required=True,
)
@click.option(
    "--config",
    "-c",
    type=click.Path(path_type=Path),
    default=Path("config/my-cluster.yaml"),
    help="Path to cluster configuration file",
)
@click.option(
    "--node",
    "-n",
    type=str,
    help="Specific node to execute on (default: best available node)",
)
@click.option(
    "--all-nodes",
    is_flag=True,
    help="Execute on all nodes",
)
@click.option(
    "--timeout",
    type=int,
    default=3600,
    help="Command timeout in seconds",
)
@click.pass_context
def execute(ctx, command, config, node, all_nodes, timeout):
    """Execute a command on cluster nodes."""
    setup_logging()
    
    async def _execute():
        try:
            cluster_config = ClusterConfig.from_yaml(config)

            # Determine target nodes first (avoid connecting to unrelated nodes)
            if all_nodes:
                target_nodes = cluster_config.nodes
            elif node:
                target_node = cluster_config.get_node_by_name(node)
                if not target_node:
                    raise click.ClickException(f"Node '{node}' not found in configuration")
                target_nodes = [target_node]
            else:
                # Execute on first available node (simplified - could implement smart selection)
                target_nodes = [cluster_config.nodes[0]]

            # Initialize SSH manager for only the target nodes
            ssh_manager = SSHManager(target_nodes)
            await ssh_manager.initialize()
            
            try:
                # Create executor
                executor = GridExecutor(ssh_manager, cluster_config.execution)
                
                if all_nodes:
                    # Execute on all nodes
                    console.print(f"[blue]Executing '{command}' on all {len(cluster_config.nodes)} nodes...[/blue]")
                    results = await executor.execute_on_nodes(command, target_nodes)
                    
                    for node_name, result in results.items():
                        console.print(f"\n[cyan]{node_name}:[/cyan]")
                        console.print(result)
                        
                elif node:
                    # Execute on specific node
                    console.print(f"[blue]Executing '{command}' on {node}...[/blue]")
                    result = await executor.execute_on_nodes(command, target_nodes)
                    console.print(result[node])
                    
                else:
                    console.print(f"[blue]Executing '{command}' on {target_nodes[0].name}...[/blue]")
                    result = await executor.execute_on_nodes(command, target_nodes)
                    console.print(result[target_nodes[0].name])
                    
            finally:
                await ssh_manager.close_all()
                
        except Exception as e:
            console.print(f"[red]Execution failed: {e}[/red]")
            raise click.ClickException(str(e))
    
    asyncio.run(_execute())


@cli.command()
def version() -> None:
    """Show version information."""
    from distributed_grid import __version__
    console.print(f"Distributed Grid v{__version__}")


@cli.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(path_type=Path),
    default=Path("config/my-cluster.yaml"),
    help="Path to cluster configuration file",
)
@click.option(
    "--resource-type",
    "-r",
    type=click.Choice(["gpu", "memory", "cpu"], case_sensitive=False),
    required=True,
    help="Type of resource to request",
)
@click.option(
    "--amount",
    "-a",
    type=int,
    required=True,
    help="Amount of resources to request",
)
@click.option(
    "--priority",
    "-p",
    type=click.Choice(["low", "medium", "high", "urgent"], case_sensitive=False),
    default="medium",
    help="Request priority",
)
@click.option(
    "--wait-time",
    "-w",
    type=int,
    default=300,
    help="Maximum wait time in seconds",
)
@click.option(
    "--job-id",
    "-j",
    type=str,
    help="Optional job ID",
)
@click.option(
    "--preferred-nodes",
    "-n",
    type=str,
    multiple=True,
    help="Preferred nodes to use",
)
@click.argument("command", nargs=-1, required=True)
def run_shared(
    config: Path,
    resource_type: str,
    amount: int,
    priority: str,
    wait_time: int,
    job_id: Optional[str],
    preferred_nodes: tuple[str, ...],
    command: tuple[str, ...],
) -> None:
    """Run a command using shared resources from any available node."""
    setup_logging()
    
    if not config.exists():
        raise click.ClickException(f"Configuration file {config} not found")
    
    async def _run_shared():
        try:
            cluster_config = ClusterConfig.from_yaml(config)
        except ValidationError as e:
            raise click.ClickException(
                f"Invalid cluster config format in {config}. "
                f"If you're using the new config schema, try -c config/my-cluster.yaml.\n\n{e}"
            )

        orchestrator = GridOrchestrator(cluster_config)
        
        try:
            await orchestrator.initialize()
            
            # Convert resource type
            rt = ResourceType(resource_type.lower())
            
            # Execute command
            console.print(
                f"[blue]Running command on shared {resource_type} resources...[/blue]"
            )
            result = await orchestrator.run_with_shared_resources(
                command=" ".join(command),
                resource_type=rt,
                amount=amount,
                priority=priority,
                max_wait_time=wait_time,
                job_id=job_id,
                preferred_nodes=list(preferred_nodes) if preferred_nodes else None,
            )
            
            console.print("[green]Command executed successfully:[/green]")
            console.print(result["output"])
            
        finally:
            await orchestrator.shutdown()
    
    asyncio.run(_run_shared())


@cli.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(path_type=Path),
    default=Path("config/my-cluster.yaml"),
    help="Path to cluster configuration file",
)
def shared_status(config: Path) -> None:
    """Show shared resource status."""
    setup_logging()
    
    if not config.exists():
        raise click.ClickException(f"Configuration file {config} not found")
    
    async def _show_status():
        try:
            cluster_config = ClusterConfig.from_yaml(config)
        except ValidationError as e:
            raise click.ClickException(
                f"Invalid cluster config format in {config}. "
                f"If you're using the new config schema, try -c config/my-cluster.yaml.\n\n{e}"
            )

        orchestrator = GridOrchestrator(cluster_config)
        
        try:
            await orchestrator.initialize()
            
            status = await orchestrator.get_shared_resource_status()
            
            # Show resource offers
            if status["offers"]:
                offers_table = Table(title="Resource Offers")
                offers_table.add_column("Node", style="cyan")
                offers_table.add_column("Type", style="magenta")
                offers_table.add_column("Available/Total", justify="right")
                offers_table.add_column("Expires", style="yellow")
                
                for offer in status["offers"]:
                    total_raw = offer.get("total", "0")
                    try:
                        total_val = float(total_raw)
                    except Exception:
                        total_val = 0.0

                    available_val = offer.get("amount", 0)
                    if offer.get("resource_type") == "memory":
                        amount_str = f"{available_val}/{int(total_val)} GB" if total_val else f"{available_val} GB"
                    elif offer.get("resource_type") == "cpu":
                        amount_str = f"{available_val}/{int(total_val)} cores" if total_val else f"{available_val} cores"
                    elif offer.get("resource_type") == "gpu":
                        amount_str = f"{available_val}/{int(total_val)} GPU" if total_val else str(available_val)

                        conditions = offer.get("conditions") or {}
                        gpu_id = conditions.get("gpu_id")
                        mem_free_mb = conditions.get("memory_free_mb")
                        mem_total_mb = conditions.get("memory_total_mb")
                        if mem_free_mb and mem_total_mb:
                            try:
                                free_gb = float(mem_free_mb) / 1024.0
                                total_gb = float(mem_total_mb) / 1024.0
                                gpu_suffix = f"GPU{gpu_id} " if gpu_id not in (None, "", "any") else ""
                                amount_str = f"{amount_str} ({gpu_suffix}{free_gb:.1f}/{total_gb:.1f} GB VRAM)"
                            except Exception:
                                pass
                    else:
                        amount_str = f"{available_val}/{int(total_val)}" if total_val else str(available_val)

                    offers_table.add_row(
                        offer["node_id"],
                        offer["resource_type"],
                        amount_str,
                        offer["available_until"],
                    )
                
                console.print(offers_table)
            else:
                console.print("[yellow]No resource offers available[/yellow]")
            
            console.print()
            
            # Show active allocations
            if status["allocations"]:
                alloc_table = Table(title="Active Allocations")
                alloc_table.add_column("Request ID", style="cyan")
                alloc_table.add_column("Node", style="magenta")
                alloc_table.add_column("Type", style="blue")
                alloc_table.add_column("Amount", justify="right")
                alloc_table.add_column("Expires", style="yellow")
                
                for alloc in status["allocations"]:
                    alloc_table.add_row(
                        alloc["request_id"],
                        alloc["node_id"],
                        alloc["resource_type"],
                        str(alloc["amount"]),
                        alloc["expires_at"],
                    )
                
                console.print(alloc_table)
            else:
                console.print("[yellow]No active allocations[/yellow]")
            
        finally:
            await orchestrator.shutdown()
    
    asyncio.run(_show_status())


@cli.group()
def offload():
    """Process offloading commands."""
    pass


@offload.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(path_type=Path),
    default=Path("config/my-cluster.yaml"),
    help="Path to cluster configuration file",
)
@click.option(
    "--node",
    "-n",
    type=str,
    help="Specific node to scan (default: all nodes)",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    help="Output format",
)
def scan(config: Path, node: Optional[str], output_format: str) -> None:
    """Scan for offloadable processes."""
    setup_logging()
    
    async def _scan():
        try:
            cluster_config = ClusterConfig.from_yaml(config)
            
            # Initialize SSH manager
            ssh_manager = SSHManager(cluster_config.nodes)
            await ssh_manager.initialize()
            
            try:
                # Initialize detector
                detector = OffloadingDetector(ssh_manager, cluster_config)
                
                # Find offloading opportunities
                recommendations = await detector.find_offloading_opportunities(node)
                
                if output_format == "json":
                    output = []
                    for rec in recommendations:
                        output.append({
                            "pid": rec.process.pid,
                            "name": rec.process.name,
                            "source": rec.source_node,
                            "target": rec.target_node,
                            "confidence": rec.confidence,
                            "reason": rec.reason,
                            "resources": rec.process.resource_requirements,
                            "complexity": rec.migration_complexity,
                        })
                    console.print(json.dumps(output, indent=2))
                else:
                    # Table format
                    table = Table(title="Offloadable Processes")
                    table.add_column("PID", justify="right")
                    table.add_column("Name")
                    table.add_column("Target Node", style="cyan")
                    table.add_column("Confidence", justify="right")
                    table.add_column("Complexity", style="yellow")
                    table.add_column("Reason")
                    
                    for rec in recommendations:
                        confidence_str = f"{rec.confidence:.1%}"
                        complexity_color = {
                            "low": "green",
                            "medium": "yellow",
                            "high": "red",
                        }.get(rec.migration_complexity, "")
                        
                        table.add_row(
                            str(rec.process.pid),
                            rec.process.name[:30] + "..." if len(rec.process.name) > 30 else rec.process.name,
                            rec.target_node,
                            confidence_str,
                            f"[{complexity_color}]{rec.migration_complexity}[/{complexity_color}]",
                            rec.reason[:50] + "..." if len(rec.reason) > 50 else rec.reason,
                        )
                    
                    console.print(table)
                    
                    if recommendations:
                        console.print(f"\n[green]Found {len(recommendations)} offloadable process(es)[/green]")
                    else:
                        console.print("\n[yellow]No offloadable processes found[/yellow]")
                
            finally:
                await ssh_manager.close_all()
                
        except Exception as e:
            console.print(f"[red]Scan failed: {e}[/red]")
            raise click.ClickException(str(e))
    
    asyncio.run(_scan())


@offload.command()
@click.argument("pid", type=int)
@click.option(
    "--config",
    "-c",
    type=click.Path(path_type=Path),
    default=Path("config/my-cluster.yaml"),
    help="Path to cluster configuration file",
)
@click.option(
    "--target-node",
    "-t",
    type=str,
    help="Target node for offloading (default: auto-select)",
)
@click.option(
    "--ray-dashboard",
    default="http://localhost:8265",
    help="Ray dashboard address",
)
@click.option(
    "--capture-state",
    is_flag=True,
    default=True,
    help="Capture process state before migration",
)
@click.option(
    "--runtime-env",
    type=str,
    help="Runtime environment JSON for Ray job",
)
def execute(
    pid: int,
    config: Path,
    target_node: Optional[str],
    ray_dashboard: str,
    capture_state: bool,
    runtime_env: Optional[str],
) -> None:
    """Offload a specific process to another node."""
    setup_logging()
    
    async def _execute():
        try:
            cluster_config = ClusterConfig.from_yaml(config)
            
            # Initialize SSH manager
            ssh_manager = SSHManager(cluster_config.nodes)
            await ssh_manager.initialize()
            
            try:
                # Initialize detector and executor
                detector = OffloadingDetector(ssh_manager, cluster_config)
                executor = OffloadingExecutor(ssh_manager, cluster_config, ray_dashboard)
                await executor.initialize()
                
                # Find the process
                recommendations = await detector.find_offloading_opportunities()
                
                # Find the specific PID
                target_rec = None
                for rec in recommendations:
                    if rec.process.pid == pid:
                        if target_node is None or rec.target_node == target_node:
                            target_rec = rec
                            break
                
                if not target_rec:
                    console.print(f"[red]Process {pid} not found or not offloadable[/red]")
                    console.print("Use 'grid offload scan' to see offloadable processes")
                    return
                
                # Parse runtime environment
                runtime_env_dict = None
                if runtime_env:
                    runtime_env_dict = json.loads(runtime_env)
                
                # Execute offloading
                console.print(f"[blue]Offloading process {pid} to {target_rec.target_node}...[/blue]")
                
                task_id = await executor.execute_offloading(
                    target_rec,
                    capture_state=capture_state,
                    runtime_env=runtime_env_dict,
                )
                
                console.print(f"[green]✓[/green] Offloading started with task ID: {task_id}")
                
                # Monitor progress
                while True:
                    task = executor.get_task_status(task_id)
                    if not task:
                        break
                    
                    if task.status.value in ["completed", "failed", "cancelled"]:
                        if task.status.value == "completed":
                            console.print(f"[green]✓[/green] Offloading completed successfully")
                        else:
                            console.print(f"[red]✗[/red] Offloading {task.status.value}")
                            if task.error_message:
                                console.print(f"Error: {task.error_message}")
                        break
                    
                    console.print(f"Status: {task.status.value}")
                    await asyncio.sleep(2)
                
            finally:
                await ssh_manager.close_all()
                
        except Exception as e:
            console.print(f"[red]Offloading failed: {e}[/red]")
            raise click.ClickException(str(e))
    
    asyncio.run(_execute())


@cli.group()
def resource_sharing():
    """Intelligent resource sharing commands."""
    pass


@resource_sharing.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    default=Path("config/my-cluster-enhanced.yaml"),
    help="Path to enhanced cluster configuration file",
)
def status(config: Path) -> None:
    """Show current resource sharing status."""
    setup_logging()

    async def _show_status():
        try:
            cluster_config = ClusterConfig.from_yaml(config)
            ssh_manager = SSHManager(cluster_config.nodes)
            orchestrator = ResourceSharingOrchestrator(cluster_config, ssh_manager)
            
            await orchestrator.initialize()
            status = await orchestrator.get_cluster_status()
            
            # Overall Status
            console.print("\n[bold]Resource Sharing Orchestrator Status[/bold]")
            console.print(f"Sharing Enabled: {'[green]Yes[/green]' if status['resource_sharing_enabled'] else '[red]No[/red]'}")
            console.print(f"Initialized: {'[green]Yes[/green]' if status['initialized'] else '[red]No[/red]'}")
            
            if status.get("resource_sharing"):
                sharing = status["resource_sharing"]
                
                # Allocation Table
                allocations_table = Table(title="Active Allocations")
                allocations_table.add_column("ID", style="dim")
                allocations_table.add_column("Node")
                allocations_table.add_column("Resource")
                allocations_table.add_column("Amount", justify="right")
                allocations_table.add_column("Priority")
                allocations_table.add_column("Expires", style="yellow")
                
                for alloc_id, alloc in sharing.get("active_allocations", {}).items():
                    allocations_table.add_row(
                        alloc_id[:8],
                        alloc["node_id"],
                        alloc["resource_type"],
                        str(alloc["amount"]),
                        alloc["priority"],
                        alloc["expires_at"]
                    )
                console.print(allocations_table)

                # Shared Resources
                resources_table = Table(title="Shared Resources Pool")
                resources_table.add_column("Node")
                resources_table.add_column("Resource")
                resources_table.add_column("Amount", justify="right")
                
                for node, res in sharing.get("shared_resources", {}).items():
                    for r_type, amt in res.items():
                        resources_table.add_row(node, r_type, str(amt))
                console.print(resources_table)

            await orchestrator.stop()
            await ssh_manager.close_all()
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    asyncio.run(_show_status())


@resource_sharing.command()
@click.option("--node", "-n", required=True, help="Node ID to request resources for")
@click.option("--type", "-t", "resource_type", type=click.Choice(["cpu", "gpu", "memory"]), required=True)
@click.option("--amount", "-a", type=float, required=True, help="Amount of resource to request")
@click.option("--priority", "-p", type=click.Choice(["low", "normal", "high", "critical"]), default="normal")
@click.option("--config", "-c", type=click.Path(exists=True, path_type=Path), default=Path("config/my-cluster-enhanced.yaml"))
def request(node: str, resource_type: str, amount: float, priority: str, config: Path) -> None:
    """Request shared resources."""
    setup_logging()

    async def _request():
        try:
            cluster_config = ClusterConfig.from_yaml(config)
            ssh_manager = SSHManager(cluster_config.nodes)
            orchestrator = ResourceSharingOrchestrator(cluster_config, ssh_manager)
            
            await orchestrator.initialize()
            allocation_id = await orchestrator.request_resources(
                node_id=node,
                resource_type=resource_type,
                amount=amount,
                priority=priority
            )
            console.print(f"[green]✓[/green] Resource allocated: [bold]{allocation_id}[/bold]")
            
            await orchestrator.stop()
            await ssh_manager.close_all()
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    asyncio.run(_request())


@resource_sharing.command()
@click.argument("allocation_id")
@click.option("--config", "-c", type=click.Path(exists=True, path_type=Path), default=Path("config/my-cluster-enhanced.yaml"))
def release(allocation_id: str, config: Path) -> None:
    """Release allocated resources."""
    setup_logging()

    async def _release():
        try:
            cluster_config = ClusterConfig.from_yaml(config)
            ssh_manager = SSHManager(cluster_config.nodes)
            orchestrator = ResourceSharingOrchestrator(cluster_config, ssh_manager)
            
            await orchestrator.initialize()
            success = await orchestrator.release_resources(allocation_id)
            
            if success:
                console.print(f"[green]✓[/green] Resources released for allocation: {allocation_id}")
            else:
                console.print(f"[red]✗[/red] Failed to release resources for allocation: {allocation_id}")
            
            await orchestrator.stop()
            await ssh_manager.close_all()
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    asyncio.run(_release())


@offload.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(path_type=Path),
    default=Path("config/my-cluster.yaml"),
    help="Path to cluster configuration file",
)
@click.option(
    "--ray-dashboard",
    default="http://localhost:8265",
    help="Ray dashboard address",
)
def status(config: Path, ray_dashboard: str) -> None:
    """Show offloading status and history."""
    setup_logging()
    
    async def _status():
        try:
            cluster_config = ClusterConfig.from_yaml(config)
            
            # Initialize SSH manager
            ssh_manager = SSHManager(cluster_config.nodes)
            await ssh_manager.initialize()
            
            try:
                # Initialize executor
                executor = OffloadingExecutor(ssh_manager, cluster_config, ray_dashboard)
                await executor.initialize()
                
                # Get statistics
                stats = await executor.get_offloading_statistics()
                
                # Show summary
                console.print("[bold]Offloading Statistics[/bold]")
                console.print(f"Total tasks: {stats['total_tasks']}")
                console.print(f"Active tasks: {stats['active_tasks']}")
                console.print(f"Completed: {stats['completed_tasks']}")
                console.print(f"Failed: {stats['failed_tasks']}")
                console.print(f"Cancelled: {stats['cancelled_tasks']}")
                
                if stats['average_duration'] > 0:
                    console.print(f"Average duration: {stats['average_duration']:.1f}s")
                
                # Show active tasks
                active_tasks = executor.list_active_tasks()
                if active_tasks:
                    console.print("\n[bold]Active Tasks[/bold]")
                    table = Table()
                    table.add_column("Task ID")
                    table.add_column("PID", justify="right")
                    table.add_column("Target")
                    table.add_column("Status")
                    table.add_column("Started")
                    
                    for task in active_tasks:
                        table.add_row(
                            task.task_id,
                            str(task.recommendation.process.pid),
                            task.recommendation.target_node,
                            task.status.value,
                            task.started_at.strftime("%H:%M:%S") if task.started_at else "",
                        )
                    
                    console.print(table)
                
                # Show recent history
                history = executor.get_task_history(limit=10)
                if history:
                    console.print("\n[bold]Recent History[/bold]")
                    table = Table()
                    table.add_column("Task ID")
                    table.add_column("PID", justify="right")
                    table.add_column("Target")
                    table.add_column("Status")
                    table.add_column("Completed")
                    
                    for task in reversed(history[-10:]):
                        status_color = {
                            "completed": "green",
                            "failed": "red",
                            "cancelled": "yellow",
                        }.get(task.status.value, "")
                        
                        table.add_row(
                            task.task_id,
                            str(task.recommendation.process.pid),
                            task.recommendation.target_node,
                            f"[{status_color}]{task.status.value}[/{status_color}]",
                            task.completed_at.strftime("%H:%M:%S") if task.completed_at else "",
                        )
                    
                    console.print(table)
                
            finally:
                await ssh_manager.close_all()
                
        except Exception as e:
            console.print(f"[red]Failed to get status: {e}[/red]")
            raise click.ClickException(str(e))
    
    asyncio.run(_status())


@offload.command()
@click.argument("task_id", type=str)
@click.option(
    "--config",
    "-c",
    type=click.Path(path_type=Path),
    default=Path("config/my-cluster.yaml"),
    help="Path to cluster configuration file",
)
@click.option(
    "--ray-dashboard",
    default="http://localhost:8265",
    help="Ray dashboard address",
)
def cancel(task_id: str, config: Path, ray_dashboard: str) -> None:
    """Cancel an active offloading task."""
    setup_logging()
    
    async def _cancel():
        try:
            cluster_config = ClusterConfig.from_yaml(config)
            
            # Initialize SSH manager
            ssh_manager = SSHManager(cluster_config.nodes)
            await ssh_manager.initialize()
            
            try:
                # Initialize executor
                executor = OffloadingExecutor(ssh_manager, cluster_config, ray_dashboard)
                await executor.initialize()
                
                # Cancel the task
                success = await executor.cancel_offloading(task_id)
                
                if success:
                    console.print(f"[green]✓[/green] Task {task_id} cancelled")
                else:
                    console.print(f"[red]✗[/red] Task {task_id} not found or already completed")
                
            finally:
                await ssh_manager.close_all()
                
        except Exception as e:
            console.print(f"[red]Failed to cancel task: {e}[/red]")
            raise click.ClickException(str(e))
    
    asyncio.run(_cancel())


@offload.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(path_type=Path),
    default=Path("config/my-cluster.yaml"),
    help="Path to cluster configuration file",
)
@click.option(
    "--interval",
    "-i",
    default=30,
    help="Monitoring interval in seconds",
)
@click.option(
    "--duration",
    "-d",
    type=int,
    help="Monitoring duration in seconds (optional)",
)
@click.option(
    "--auto-heal",
    is_flag=True,
    help="Enable automatic healing of failed nodes",
)
@click.option(
    "--alert-threshold",
    default=3,
    help="Number of consecutive failures before alert",
)
def monitor(config: Path, interval: int, duration: Optional[int], auto_heal: bool, alert_threshold: int) -> None:
    """Monitor Ray cluster heartbeat health."""
    setup_logging()
    
    # Import and run the heartbeat monitor
    import sys
    from pathlib import Path
    
    # Add the project root to the path
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))
    
    from scripts.monitor_heartbeat import HeartbeatMonitor
    
    monitor = HeartbeatMonitor(config)
    monitor.alert_threshold = alert_threshold
    
    asyncio.run(monitor.start_monitoring(interval, duration, auto_heal))


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
