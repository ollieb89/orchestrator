#!/usr/bin/env python3
"""Demo script for intelligent resource sharing system."""

import asyncio
import logging
import time
from datetime import datetime, UTC
from pathlib import Path
import sys

import ray
import yaml
import structlog
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from distributed_grid.config import ClusterConfig
from distributed_grid.core.ssh_manager import SSHManager
from distributed_grid.orchestration.resource_sharing_orchestrator import (
    ResourceSharingOrchestrator,
)
from distributed_grid.monitoring.resource_metrics import ResourceType
from distributed_grid.orchestration.offloading_detector import (
    ProcessInfo,
    ProcessType,
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger(__name__)

# Rich console
console = Console()


class ResourceSharingDemo:
    """Demo application for intelligent resource sharing."""
    
    def __init__(self, config_path: str):
        """Initialize the demo."""
        self.config_path = config_path
        self.config = self._load_config()
        self.orchestrator = None
        self.console = Console()
        
    def _load_config(self) -> ClusterConfig:
        """Load cluster configuration."""
        with open(self.config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        return ClusterConfig(**config_data)
        
    async def start(self):
        """Start the demo."""
        self.console.print("\n[bold blue]Intelligent Resource Sharing Demo[/bold blue]")
        self.console.print("=" * 50)
        
        # Create SSH manager
        ssh_manager = SSHManager()
        
        # Create orchestrator
        self.orchestrator = ResourceSharingOrchestrator(
            self.config,
            ssh_manager,
            ray_dashboard_address="http://localhost:8265",
        )
        
        try:
            # Initialize
            self.console.print("\n[yellow]Initializing resource sharing system...[/yellow]")
            await self.orchestrator.initialize()
            await self.orchestrator.start()
            self.console.print("[green]✓[/green] Resource sharing system initialized")
            
            # Run demo scenarios
            await self._run_demo_scenarios()
            
        except Exception as e:
            self.console.print(f"\n[red]Error: {e}[/red]")
            logger.error("Demo failed", error=e)
            
        finally:
            # Cleanup
            if self.orchestrator:
                await self.orchestrator.stop()
                self.console.print("\n[yellow]Resource sharing system stopped[/yellow]")
                
    async def _run_demo_scenarios(self):
        """Run various demo scenarios."""
        scenarios = [
            ("Cluster Status Overview", self._demo_cluster_status),
            ("Resource Monitoring", self._demo_resource_monitoring),
            ("Resource Request and Allocation", self._demo_resource_allocation),
            ("Intelligent Task Scheduling", self._demo_task_scheduling),
            ("Dynamic Load Balancing", self._demo_load_balancing),
        ]
        
        for name, func in scenarios:
            self.console.print(f"\n[bold cyan]Scenario: {name}[/bold cyan]")
            self.console.print("-" * 40)
            await func()
            self.console.print("\n[dim]Press Enter to continue...[/dim]")
            input()
            
    async def _demo_cluster_status(self):
        """Demo cluster status overview."""
        # Get cluster status
        status = await self.orchestrator.get_cluster_status()
        
        # Create status table
        table = Table(title="Cluster Status")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Resource Sharing", "Enabled" if status["resource_sharing_enabled"] else "Disabled")
        table.add_row("Total Nodes", str(status.get("metrics", {}).get("total_nodes", 0)))
        table.add_row("Total CPUs", str(status.get("metrics", {}).get("total_cpu", 0)))
        table.add_row("Total GPUs", str(status.get("metrics", {}).get("total_gpu", 0)))
        table.add_row("CPU Utilization", f"{status.get('metrics', {}).get('cpu_utilization', 0):.1f}%")
        table.add_row("Memory Utilization", f"{status.get('metrics', {}).get('memory_utilization', 0):.1f}%")
        table.add_row("GPU Utilization", f"{status.get('metrics', {}).get('gpu_utilization', 0):.1f}%")
        
        self.console.print(table)
        
        # Node pressure scores
        pressure_scores = status.get("metrics", {}).get("node_pressure_scores", {})
        if pressure_scores:
            pressure_table = Table(title="Node Pressure Scores")
            pressure_table.add_column("Node", style="cyan")
            pressure_table.add_column("Pressure", style="yellow")
            pressure_table.add_column("Status", style="green")
            
            for node, pressure in pressure_scores.items():
                if pressure < 0.3:
                    status_text = "[green]Low[/green]"
                elif pressure < 0.7:
                    status_text = "[yellow]Medium[/yellow]"
                else:
                    status_text = "[red]High[/red]"
                pressure_table.add_row(node, f"{pressure:.2f}", status_text)
                
            self.console.print(pressure_table)
            
    async def _demo_resource_monitoring(self):
        """Demo real-time resource monitoring."""
        snapshots = self.orchestrator.get_node_resource_snapshots()
        
        # Create resource table
        table = Table(title="Resource Snapshots")
        table.add_column("Node", style="cyan")
        table.add_column("CPU", style="blue")
        table.add_column("Memory (GB)", style="blue")
        table.add_column("GPU", style="blue")
        table.add_column("Pressure", style="yellow")
        
        for node_id, snapshot in snapshots.items():
            cpu_info = f"{snapshot['cpu']['used']:.1f}/{snapshot['cpu']['total']} ({snapshot['cpu']['percent']:.1f}%)"
            memory_info = f"{snapshot['memory']['used_gb']:.1f}/{snapshot['memory']['total_gb']:.1f} ({snapshot['memory']['percent']:.1f}%)"
            gpu_info = f"{snapshot['gpu']['used']}/{snapshot['gpu']['total']}"
            pressure = f"{snapshot['pressure']['overall']:.2f}"
            
            table.add_row(node_id, cpu_info, memory_info, gpu_info, pressure)
            
        self.console.print(table)
        
        # Show trends
        self.console.print("\n[yellow]Simulating resource pressure changes...[/yellow]")
        
        # Simulate increasing load
        for i in range(5):
            await asyncio.sleep(1)
            self.console.print(f".", end="")
            
        self.console.print("\n[green]Resource trends updated[/green]")
        
    async def _demo_resource_allocation(self):
        """Demo resource request and allocation."""
        self.console.print("[yellow]Requesting shared resources...[/yellow]")
        
        # Request CPU resources
        request_id = await self.orchestrator.request_resources(
            node_id="gpu-master",
            resource_type="cpu",
            amount=2.0,
            priority="high",
            duration_minutes=5,
        )
        
        self.console.print(f"[green]✓[/green] CPU request submitted: {request_id}")
        
        # Request memory resources
        memory_request = await self.orchestrator.request_resources(
            node_id="gpu-master",
            resource_type="memory",
            amount=4 * 1024**3,  # 4GB
            priority="normal",
            duration_minutes=10,
        )
        
        self.console.print(f"[green]✓[/green] Memory request submitted: {memory_request}")
        
        # Show allocation status
        await asyncio.sleep(2)
        status = await self.orchestrator.get_cluster_status()
        allocations = status.get("resource_sharing", {}).get("active_allocations", 0)
        
        self.console.print(f"\n[blue]Active allocations: {allocations}[/blue]")
        
    async def _demo_task_scheduling(self):
        """Demo intelligent task scheduling."""
        self.console.print("[yellow]Simulating task scheduling decisions...[/yellow]")
        
        # Create mock tasks with different requirements
        tasks = [
            {"name": "ML Training", "cpu": 4, "memory": 8192, "gpu": 1, "priority": "high"},
            {"name": "Data Processing", "cpu": 2, "memory": 4096, "gpu": 0, "priority": "normal"},
            {"name": "Inference", "cpu": 1, "memory": 2048, "gpu": 1, "priority": "normal"},
            {"name": "Batch Job", "cpu": 6, "memory": 16384, "gpu": 0, "priority": "low"},
        ]
        
        # Create scheduling table
        table = Table(title="Task Scheduling Decisions")
        table.add_column("Task", style="cyan")
        table.add_column("Requirements", style="blue")
        table.add_column("Assigned Node", style="green")
        table.add_column("Confidence", style="yellow")
        table.add_column("Reasoning", style="dim")
        
        for task in tasks:
            # Simulate scheduling decision
            if task["gpu"] > 0:
                node = "gpu-master" if task["priority"] == "high" else "gpu1"
                confidence = 0.85
                reasoning = "GPU available, high priority"
            elif task["cpu"] > 4:
                node = "gpu2"
                confidence = 0.75
                reasoning = "High CPU requirement"
            else:
                node = "gpu-master"
                confidence = 0.90
                reasoning = "Low load, available resources"
                
            req_str = f"C:{task['cpu']} M:{task['memory']//1024}G G:{task['gpu']}"
            
            table.add_row(
                task["name"],
                req_str,
                node,
                f"{confidence:.0%}",
                reasoning,
            )
            
        self.console.print(table)
        
    async def _demo_load_balancing(self):
        """Demo dynamic load balancing."""
        self.console.print("[yellow]Simulating dynamic load balancing...[/yellow]")
        
        # Show initial state
        snapshots = self.orchestrator.get_node_resource_snapshots()
        
        balance_table = Table(title="Load Balancing Actions")
        balance_table.add_column("Action", style="cyan")
        balance_table.add_column("Source", style="blue")
        balance_table.add_column("Target", style="green")
        balance_table.add_column("Resource", style="yellow")
        balance_table.add_column("Amount", style="magenta")
        
        # Simulate load balancing actions
        actions = [
            {
                "action": "Resource Request",
                "source": "gpu-master (high load)",
                "target": "gpu1",
                "resource": "CPU",
                "amount": "2 cores",
            },
            {
                "action": "Resource Sharing",
                "source": "gpu2 (excess)",
                "target": "gpu-master",
                "resource": "Memory",
                "amount": "4GB",
            },
            {
                "action": "Task Migration",
                "source": "gpu-master",
                "target": "gpu1",
                "resource": "GPU Task",
                "amount": "1 GPU",
            },
        ]
        
        for action in actions:
            balance_table.add_row(
                action["action"],
                action["source"],
                action["target"],
                action["resource"],
                action["amount"],
            )
            
        self.console.print(balance_table)
        
        # Show rebalancing effect
        self.console.print("\n[green]Load rebalanced successfully![/green]")
        self.console.print("[dim]Resources distributed based on node pressure and availability[/dim]")


async def main():
    """Main demo entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Intelligent Resource Sharing Demo")
    parser.add_argument(
        "--config",
        default="config/my-cluster-enhanced.yaml",
        help="Cluster configuration file",
    )
    
    args = parser.parse_args()
    
    # Check if config exists
    config_path = Path(args.config)
    if not config_path.exists():
        console.print(f"[red]Configuration file not found: {config_path}[/red]")
        console.print("[yellow]Using default configuration...[/yellow]")
        config_path = Path("config/my-cluster.yaml")
        
    # Run demo
    demo = ResourceSharingDemo(str(config_path))
    await demo.start()


if __name__ == "__main__":
    # Run demo
    asyncio.run(main())
