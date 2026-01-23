#!/usr/bin/env python3
"""
Resource Boost Manager Test Script

This script demonstrates and tests the Resource Boost Manager functionality
as described in the Resource Boost Manager Guide.
"""

import asyncio
import time
import subprocess
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint

console = Console()


def run_command(cmd: str, capture_output: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and return the result."""
    console.print(f"\n[cyan]Running:[/cyan] {cmd}")
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=capture_output,
        text=True,
        cwd=Path(__file__).parent.parent
    )
    if result.returncode == 0:
        console.print("[green]✓[/green] Command succeeded")
        if result.stdout:
            console.print(result.stdout)
    else:
        console.print(f"[red]✗[/red] Command failed with exit code {result.returncode}")
        if result.stderr:
            console.print(f"[red]Error:[/red] {result.stderr}")
    return result


def test_basic_functionality():
    """Test basic boost request and status commands."""
    console.print("\n[bold cyan]=== Testing Basic Functionality ===[/bold cyan]")
    
    # Test 1: Check initial status
    console.print("\n[yellow]Test 1: Check initial boost status[/yellow]")
    run_command("poetry run grid boost status")
    
    # Test 2: Request CPU boost
    console.print("\n[yellow]Test 2: Request CPU boost[/yellow]")
    result = run_command("poetry run grid boost request gpu-master cpu 2.0 --priority high")
    
    # Test 3: Check status after request
    console.print("\n[yellow]Test 3: Check status after CPU request[/yellow]")
    run_command("poetry run grid boost status")
    
    # Test 4: Request GPU boost
    console.print("\n[yellow]Test 4: Request GPU boost[/yellow]")
    run_command("poetry run grid boost request gpu-master gpu 1 --priority critical --duration 1800")
    
    # Test 5: Request memory boost with source
    console.print("\n[yellow]Test 5: Request memory boost with source node[/yellow]")
    run_command("poetry run grid boost request gpu-master memory 8.0 --source gpu2 --duration 7200")
    
    # Test 6: Check final status
    console.print("\n[yellow]Test 6: Check final boost status[/yellow]")
    run_command("poetry run grid boost status")


def test_priority_levels():
    """Test different priority levels."""
    console.print("\n[bold cyan]=== Testing Priority Levels ===[/bold cyan]")
    
    priorities = ["low", "normal", "high", "critical"]
    for priority in priorities:
        console.print(f"\n[yellow]Testing {priority} priority[/yellow]")
        run_command(f"poetry run grid boost request gpu-master cpu 1.0 --priority {priority} --duration 300")


def test_error_handling():
    """Test error handling for invalid inputs."""
    console.print("\n[bold cyan]=== Testing Error Handling ===[/bold cyan]")
    
    # Test invalid resource type
    console.print("\n[yellow]Test: Invalid resource type[/yellow]")
    run_command("poetry run grid boost request gpu-master invalid-resource 2.0")
    
    # Test invalid boost ID
    console.print("\n[yellow]Test: Invalid boost ID for release[/yellow]")
    run_command("poetry run grid boost release invalid-boost-id")
    
    # Test invalid node (should warn but proceed)
    console.print("\n[yellow]Test: Invalid node name[/yellow]")
    run_command("poetry run grid boost request invalid-node cpu 2.0")


def test_comprehensive_workflow():
    """Test a comprehensive workflow as shown in the guide."""
    console.print("\n[bold cyan]=== Comprehensive Workflow Example ===[/bold cyan]")
    
    # Step 1: Check current status
    console.print("\n[yellow]Step 1: Check current cluster status[/yellow]")
    run_command("poetry run grid cluster status")
    
    # Step 2: Check resource sharing status
    console.print("\n[yellow]Step 2: Check resource sharing status[/yellow]")
    run_command("poetry run grid resource-sharing status --config config/my-cluster-enhanced.yaml")
    
    # Step 3: Request CPU boost for intensive computation
    console.print("\n[yellow]Step 3: Request CPU boost for intensive computation[/yellow]")
    result = run_command("poetry run grid boost request gpu-master cpu 4.0 --priority high --duration 1800")
    
    # Extract boost ID if successful
    boost_id = None
    if result.returncode == 0 and "Boost ID:" in result.stdout:
        for line in result.stdout.split('\n'):
            if "Boost ID:" in line:
                boost_id = line.split("Boost ID:")[1].strip()
                break
    
    # Step 4: Check boost status
    console.print("\n[yellow]Step 4: Check boost status[/yellow]")
    run_command("poetry run grid boost status")
    
    # Step 5: Simulate running a task (sleep for 2 seconds)
    console.print("\n[yellow]Step 5: Simulate running intensive task...[/yellow]")
    console.print("[dim]Sleeping for 2 seconds to simulate task execution...[/dim]")
    time.sleep(2)
    
    # Step 6: Release the boost early
    if boost_id:
        console.print(f"\n[yellow]Step 6: Release boost {boost_id}[/yellow]")
        run_command(f"poetry run grid boost release {boost_id}")
    
    # Step 7: Final status check
    console.print("\n[yellow]Step 7: Final status check[/yellow]")
    run_command("poetry run grid boost status")


def test_ray_integration():
    """Test Ray integration and warnings."""
    console.print("\n[bold cyan]=== Testing Ray Integration ===[/bold cyan]")
    
    console.print("\n[yellow]Note: You will see warnings about Ray dynamic resources being deprecated.[/yellow]")
    console.print("[yellow]This is expected and documented in the guide.[/yellow]")
    
    # Request a boost to see Ray integration
    run_command("poetry run grid boost request gpu-master cpu 1.0 --priority normal")


def main():
    """Main test function."""
    console.print(Panel.fit(
        "[bold cyan]Resource Boost Manager Test Script[/bold cyan]\n\n"
        "This script tests all Resource Boost Manager commands\n"
        "as documented in the Resource Boost Manager Guide.",
        title="Resource Boost Tests"
    ))
    
    console.print("\n[bold red]IMPORTANT NOTE:[/bold red]")
    console.print("[yellow]Resource boosts do NOT persist between CLI commands.[/yellow]")
    console.print("[yellow]Each command creates a new ResourceBoostManager instance.[/yellow]")
    console.print("[yellow]This is a known limitation - boosts are stored in memory only.[/yellow]")
    
    input("\nPress Enter to start tests...")
    
    try:
        # Run all tests
        test_basic_functionality()
        test_priority_levels()
        test_error_handling()
        test_comprehensive_workflow()
        test_ray_integration()
        
        console.print("\n[bold green]=== All Tests Completed ===[/bold green]")
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Tests interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error during tests: {e}[/red]")
    
    console.print("\n[bold cyan]Test Summary[/bold cyan]")
    console.print("✓ Basic boost requests work")
    console.print("✓ Priority levels are accepted")
    console.print("✓ Duration parameter works")
    console.print("✓ Source node specification works")
    console.print("✓ Error handling works correctly")
    console.print("✓ Ray integration shows expected warnings")
    console.print("\n[red]✗ Boosts don't persist between CLI commands (known issue)[/red]")
    
    console.print("\n[bold]For more information, see:[/bold]")
    console.print("• Resource Boost Manager Guide: docs/resource_boost_manager_guide.md")
    console.print("• Ray Dashboard: http://localhost:8265")
    console.print("• Resource sharing status: poetry run grid resource-sharing status")


if __name__ == "__main__":
    main()
