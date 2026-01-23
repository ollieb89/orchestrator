#!/usr/bin/env python3
"""
Resource Boost Demo Script

This script demonstrates the ResourceBoostManager's capabilities for:
1. Requesting CPU boosts from worker nodes
2. Requesting GPU boosts for accelerated tasks
3. Requesting memory boosts for memory-intensive operations
4. Monitoring boost status and releasing resources

Usage:
    poetry run python examples/resource_boost_demo.py
"""

import asyncio
import time
import os
import sys
from pathlib import Path
from typing import Dict, Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import ray
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

from distributed_grid.config.models import ClusterConfig
from distributed_grid.orchestration.resource_boost_manager import (
    ResourceBoostManager,
    ResourceBoostRequest,
    ResourceType,
    AllocationPriority
)
from distributed_grid.monitoring.resource_metrics import ResourceMetricsCollector
from distributed_grid.orchestration.resource_sharing_manager import ResourceSharingManager
from distributed_grid.utils.logging import setup_logging

console = Console()


class ResourceBoostDemo:
    """Interactive demo for resource boosting capabilities."""
    
    def __init__(self, config_path: Path = Path("config/my-cluster-enhanced.yaml")):
        """Initialize the demo.
        
        Args:
            config_path: Path to cluster configuration
        """
        self.config_path = config_path
        self.cluster_config = None
        self.boost_manager = None
        self.metrics_collector = None
        self.resource_sharing_manager = None
        
    async def initialize(self):
        """Initialize all components."""
        console.print("[bold green]Initializing Resource Boost Demo[/bold green]")
        
        # Setup logging
        setup_logging()
        
        # Initialize Ray
        if not ray.is_initialized():
            ray.init(address="auto")
            console.print("✓ Connected to Ray cluster")
        
        # Load configuration
        self.cluster_config = ClusterConfig.from_yaml(self.config_path)
        console.print(f"✓ Loaded cluster config: {self.cluster_config.name}")
        
        # Initialize components
        self.metrics_collector = ResourceMetricsCollector(self.cluster_config)
        await self.metrics_collector.start()
        console.print("✓ Initialized metrics collector")
        
        self.resource_sharing_manager = ResourceSharingManager(
            cluster_config=self.cluster_config,
            metrics_collector=self.metrics_collector
        )
        await self.resource_sharing_manager.start()
        console.print("✓ Initialized resource sharing manager")
        
        self.boost_manager = ResourceBoostManager(
            cluster_config=self.cluster_config,
            metrics_collector=self.metrics_collector,
            resource_sharing_manager=self.resource_sharing_manager
        )
        await self.boost_manager.initialize()
        console.print("✓ Initialized resource boost manager")
        
        console.print()
    
    async def show_cluster_status(self):
        """Display current cluster resource status."""
        console.print("[bold]Cluster Resource Status[/bold]")
        
        # Get cluster resources
        cluster_resources = ray.cluster_resources()
        
        table = Table(title="Available Resources")
        table.add_column("Resource", style="cyan")
        table.add_column("Total", justify="right")
        table.add_column("Available", justify="right")
        
        for resource, amount in cluster_resources.items():
            if resource in ["CPU", "GPU", "memory"]:
                available = ray.available_resources().get(resource, 0)
                if resource == "memory":
                    amount_str = f"{amount / (1024**3):.1f} GB"
                    available_str = f"{available / (1024**3):.1f} GB"
                else:
                    amount_str = str(int(amount))
                    available_str = str(int(available))
                table.add_row(resource, amount_str, available_str)
        
        console.print(table)
        console.print()
    
    async def demo_cpu_boost(self):
        """Demonstrate CPU resource boosting."""
        console.print(Panel("[bold cyan]CPU Boost Demo[/bold cyan]", expand=False))
        
        # Show initial status
        console.print("Initial CPU status:")
        await self.show_cluster_status()
        
        # Request CPU boost
        console.print("\n[yellow]Requesting 2 CPU cores from worker nodes...[/yellow]")
        request = ResourceBoostRequest(
            target_node="gpu-master",
            resource_type=ResourceType.CPU,
            amount=2.0,
            priority=AllocationPriority.HIGH,
            duration_seconds=300  # 5 minutes
        )
        
        boost_id = await self.boost_manager.request_boost(request)
        
        if boost_id:
            console.print(f"[green]✓ CPU boost requested: {boost_id}[/green]")
            
            # Show updated status
            await asyncio.sleep(2)
            console.print("\nStatus after CPU boost:")
            await self.show_cluster_status()
            
            # Simulate using the boosted resources
            console.print("\n[yellow]Simulating CPU-intensive task...[/yellow]")
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Processing with boosted CPUs...", total=100)
                for i in range(100):
                    await asyncio.sleep(0.05)
                    progress.update(task, advance=1)
            
            console.print("[green]✓ Task completed with boosted resources[/green]")
            
            # Release the boost
            console.print(f"\n[yellow]Releasing CPU boost {boost_id}...[/yellow]")
            success = await self.boost_manager.release_boost(boost_id)
            if success:
                console.print("[green]✓ CPU boost released[/green]")
        else:
            console.print("[red]✗ Failed to request CPU boost[/red]")
        
        console.print()
    
    async def demo_gpu_boost(self):
        """Demonstrate GPU resource boosting."""
        console.print(Panel("[bold magenta]GPU Boost Demo[/bold magenta]", expand=False))
        
        # Request GPU boost
        console.print("\n[yellow]Requesting 1 GPU from worker nodes...[/yellow]")
        request = ResourceBoostRequest(
            target_node="gpu-master",
            resource_type=ResourceType.GPU,
            amount=1.0,
            priority=AllocationPriority.CRITICAL,
            duration_seconds=600  # 10 minutes
        )
        
        boost_id = await self.boost_manager.request_boost(request)
        
        if boost_id:
            console.print(f"[green]✓ GPU boost requested: {boost_id}[/green]")
            
            # Show boost status
            await asyncio.sleep(2)
            boosts = await self.boost_manager.get_active_boosts()
            if boosts:
                table = Table(title="Active GPU Boosts")
                table.add_column("Boost ID", style="cyan")
                table.add_column("Source", justify="center")
                table.add_column("Target", justify="center")
                table.add_column("Resource", justify="center")
                table.add_column("Amount", justify="right")
                
                for boost in boosts:
                    if boost.resource_type == ResourceType.GPU:
                        table.add_row(
                            boost.boost_id[:8] + "...",
                            boost.source_node,
                            boost.target_node,
                            boost.resource_type.value,
                            str(boost.amount)
                        )
                
                console.print(table)
            
            # Simulate GPU task
            console.print("\n[yellow]Simulating GPU-accelerated task...[/yellow]")
            
            # Create a simple Ray task that uses GPU
            @ray.remote(num_gpus=1)
            def gpu_task():
                import time
                time.sleep(2)
                return "GPU task completed successfully"
            
            try:
                future = gpu_task.remote()
                result = ray.get(future)
                console.print(f"[green]✓ {result}[/green]")
            except Exception as e:
                console.print(f"[red]GPU task failed: {e}[/red]")
            
            # Release the boost
            console.print(f"\n[yellow]Releasing GPU boost {boost_id}...[/yellow]")
            success = await self.boost_manager.release_boost(boost_id)
            if success:
                console.print("[green]✓ GPU boost released[/green]")
        else:
            console.print("[red]✗ Failed to request GPU boost[/red]")
        
        console.print()
    
    async def demo_memory_boost(self):
        """Demonstrate memory resource boosting."""
        console.print(Panel("[bold blue]Memory Boost Demo[/bold blue]", expand=False))
        
        # Request memory boost
        console.print("\n[yellow]Requesting 4 GB memory from worker nodes...[/yellow]")
        request = ResourceBoostRequest(
            target_node="gpu-master",
            resource_type=ResourceType.MEMORY,
            amount=4.0,  # 4 GB
            priority=AllocationPriority.NORMAL,
            duration_seconds=900  # 15 minutes
        )
        
        boost_id = await self.boost_manager.request_boost(request)
        
        if boost_id:
            console.print(f"[green]✓ Memory boost requested: {boost_id}[/green]")
            
            # Simulate memory-intensive task
            console.print("\n[yellow]Simulating memory-intensive task...[/yellow]")
            
            @ray.remote
            def memory_task():
                # Allocate memory
                data = bytearray(1024 * 1024 * 1024)  # 1 GB
                import time
                time.sleep(2)
                return f"Processed {len(data) / (1024**2):.0f} MB of data"
            
            try:
                future = memory_task.remote()
                result = ray.get(future)
                console.print(f"[green]✓ {result}[/green]")
            except Exception as e:
                console.print(f"[red]Memory task failed: {e}[/red]")
            
            # Release the boost
            console.print(f"\n[yellow]Releasing memory boost {boost_id}...[/yellow]")
            success = await self.boost_manager.release_boost(boost_id)
            if success:
                console.print("[green]✓ Memory boost released[/green]")
        else:
            console.print("[red]✗ Failed to request memory boost[/red]")
        
        console.print()
    
    async def show_boost_summary(self):
        """Display summary of all boost operations."""
        console.print(Panel("[bold]Resource Boost Summary[/bold]", expand=False))
        
        # Get overall status
        status = await self.boost_manager.get_boost_status()
        
        console.print(f"Total Active Boosts: {status['total_active_boosts']}")
        
        if status['boosted_resources']:
            console.print("\n[bold]Currently Boosted Resources:[/bold]")
            for rtype, amount in status['boosted_resources'].items():
                console.print(f"  • {rtype}: {amount}")
        
        # Show Ray cluster resources
        console.print("\n[bold]Final Cluster Resources:[/bold]")
        cluster_resources = ray.cluster_resources()
        for resource, amount in cluster_resources.items():
            if resource.startswith("boost_"):
                console.print(f"  • {resource}: {amount}")
        
        console.print()
    
    async def run_demo(self):
        """Run the complete demo."""
        try:
            await self.initialize()
            
            console.print(Panel(
                "[bold green]Resource Boost Demo[/bold green]\n\n"
                "This demo showcases the ResourceBoostManager's ability to:\n"
                "• Dynamically request CPU resources from worker nodes\n"
                "• Borrow GPU resources for accelerated tasks\n"
                "• Allocate additional memory for intensive operations\n"
                "• Monitor and release resources when done",
                title="Welcome",
                expand=False
            ))
            
            # Run individual demos
            await self.demo_cpu_boost()
            await self.demo_gpu_boost()
            await self.demo_memory_boost()
            
            # Show final summary
            await self.show_boost_summary()
            
            console.print("[bold green]Demo completed successfully![/bold green]")
            
        except Exception as e:
            console.print(f"[red]Demo failed: {e}[/red]")
            import traceback
            console.print(traceback.format_exc())
        
        finally:
            # Clean up
            if ray.is_initialized():
                ray.shutdown()


async def main():
    """Main entry point."""
    demo = ResourceBoostDemo()
    await demo.run_demo()


if __name__ == "__main__":
    asyncio.run(main())
