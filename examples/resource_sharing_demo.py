#!/usr/bin/env python3
"""Demo script showing resource sharing capabilities."""

import asyncio
import logging
from pathlib import Path

from distributed_grid.core import GridOrchestrator
from distributed_grid.config import ClusterConfig
from distributed_grid.orchestration.resource_sharing import ResourceType, ResourceRequest
from distributed_grid.utils.logging import setup_logging

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


async def demo_resource_sharing():
    """Demonstrate resource sharing functionality."""
    # Load configuration
    config_path = Path(__file__).parent.parent / "config" / "cluster_config.yaml"
    config = ClusterConfig.from_yaml(config_path)
    
    # Create orchestrator
    orchestrator = GridOrchestrator(config)
    
    try:
        # Initialize
        logger.info("Initializing orchestrator...")
        await orchestrator.initialize()
        
        # Show initial resource status
        logger.info("Checking shared resource status...")
        status = await orchestrator.get_shared_resource_status()
        
        print("\n=== Current Resource Offers ===")
        if status["offers"]:
            for offer in status["offers"]:
                print(f"Node {offer['node_id']}: {offer['amount']} {offer['resource_type']}")
        else:
            print("No resource offers available")
        
        print("\n=== Active Allocations ===")
        if status["allocations"]:
            for alloc in status["allocations"]:
                print(f"Request {alloc['request_id']}: {alloc['amount']} {alloc['resource_type']} on {alloc['node_id']}")
        else:
            print("No active allocations")
        
        # Example 1: Request a GPU for a training job
        print("\n=== Example 1: Requesting GPU for training ===")
        try:
            result = await orchestrator.run_with_shared_resources(
                command="python3 -c 'import torch; print(f\"CUDA available: {torch.cuda.is_available()}\"); print(f\"GPU count: {torch.cuda.device_count()}\")' if torch.cuda.is_available() else print(\"CUDA not available\")",
                resource_type=ResourceType.GPU,
                amount=1,
                priority="high",
                job_id="training_job_001",
            )
            print("Training job result:")
            print(result["output"])
        except Exception as e:
            print(f"Failed to run training job: {e}")
        
        # Example 2: Request memory for a data processing task
        print("\n=== Example 2: Requesting memory for data processing ===")
        try:
            result = await orchestrator.run_with_shared_resources(
                command="python3 -c 'import psutil; mem = psutil.virtual_memory(); print(f\"Available memory: {mem.available / (1024**3):.2f} GB\")'",
                resource_type=ResourceType.MEMORY,
                amount=4,  # Request 4 GB
                priority="medium",
                job_id="data_processing_001",
            )
            print("Data processing result:")
            print(result["output"])
        except Exception as e:
            print(f"Failed to run data processing job: {e}")
        
        # Example 3: Request CPU cores for a parallel task
        print("\n=== Example 3: Requesting CPU cores for parallel task ===")
        try:
            result = await orchestrator.run_with_shared_resources(
                command="python3 -c 'import multiprocessing; print(f\"Available CPU cores: {multiprocessing.cpu_count()}\")'",
                resource_type=ResourceType.CPU,
                amount=2,  # Request 2 cores
                priority="low",
                job_id="parallel_task_001",
            )
            print("Parallel task result:")
            print(result["output"])
        except Exception as e:
            print(f"Failed to run parallel task: {e}")
        
        # Show final status
        print("\n=== Final Resource Status ===")
        status = await orchestrator.get_shared_resource_status()
        
        if status["offers"]:
            print("Available offers:")
            for offer in status["offers"]:
                print(f"  Node {offer['node_id']}: {offer['amount']} {offer['resource_type']}")
        
        if status["allocations"]:
            print("Active allocations:")
            for alloc in status["allocations"]:
                print(f"  Request {alloc['request_id']}: {alloc['amount']} {alloc['resource_type']} on {alloc['node_id']}")
    
    finally:
        # Cleanup
        logger.info("Shutting down orchestrator...")
        await orchestrator.shutdown()


async def demo_resource_monitoring():
    """Demonstrate resource monitoring on worker nodes."""
    from distributed_grid.orchestration.resource_sharing import ResourceSharingProtocol
    from distributed_grid.core.ssh_manager import SSHManager
    
    config_path = Path(__file__).parent.parent / "config" / "cluster_config.yaml"
    config = ClusterConfig.from_yaml(config_path)
    
    ssh_manager = SSHManager(config.nodes)
    protocol = ResourceSharingProtocol(ssh_manager)
    
    try:
        await ssh_manager.initialize()
        
        # Install worker agents if not already installed
        for node in config.nodes[:2]:  # Test on first 2 nodes
            logger.info(f"Installing worker agent on {node.name}...")
            success = await protocol.install_worker_agent(node.name)
            if success:
                logger.info(f"Worker agent installed on {node.name}")
            else:
                logger.error(f"Failed to install worker agent on {node.name}")
        
        # Check resources on nodes
        for node in config.nodes[:2]:
            logger.info(f"Checking resources on {node.name}...")
            resources = await protocol.check_node_resources(
                node.name,
                thresholds={
                    "gpu_utilization_max": 50,
                    "memory_percent_max": 70,
                    "cpu_percent_max": 50,
                }
            )
            
            if resources:
                print(f"\n=== Resources on {node.name} ===")
                print(f"Status: {resources.get('status', {})}")
                print(f"Offers: {resources.get('offers', [])}")
    
    finally:
        await ssh_manager.close_all()


if __name__ == "__main__":
    print("=== Resource Sharing Demo ===\n")
    
    # Run main demo
    asyncio.run(demo_resource_sharing())
    
    print("\n" + "="*50 + "\n")
    
    # Run monitoring demo
    print("=== Resource Monitoring Demo ===\n")
    asyncio.run(demo_resource_monitoring())
