#!/usr/bin/env python3
"""
Example usage of the Intelligent Resource Sharing system.
This script demonstrates how to initialize the orchestrator and request shared resources.
"""

import asyncio
import logging
from pathlib import Path

import structlog
from distributed_grid.config import load_config
from distributed_grid.core.ssh_manager import SSHManager
from distributed_grid.orchestration.resource_sharing_orchestrator import ResourceSharingOrchestrator

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

async def main():
    # 1. Load the enhanced cluster configuration
    config_path = Path("config/my-cluster-enhanced.yaml")
    if not config_path.exists():
        logger.error("Configuration file not found", path=str(config_path))
        return

    cluster_config = load_config(config_path)
    
    # 2. Initialize SSH Manager (required for remote operations)
    ssh_manager = SSHManager(cluster_config.nodes)
    
    # 3. Initialize the Resource Sharing Orchestrator
    logger.info("Initializing ResourceSharingOrchestrator...")
    orchestrator = ResourceSharingOrchestrator(
        cluster_config, 
        ssh_manager,
        ray_dashboard_address="http://localhost:8265"
    )
    
    try:
        await orchestrator.initialize()
        await orchestrator.start()
        
        # 4. Request shared resources
        # Scenario: Master node (gpu-master) needs more CPU to coordinate tasks
        logger.info("Requesting shared resources for gpu-master...")
        allocation_id = await orchestrator.request_resources(
            node_id="gpu-master",
            resource_type="cpu",
            amount=2.0,
            priority="high",
            duration_minutes=15
        )
        
        logger.info("Resource allocation successful", allocation_id=allocation_id)
        
        # 5. Get cluster status to verify allocation
        status = await orchestrator.get_cluster_status()
        logger.info("Current Cluster Status", status=status)
        
        # 6. Wait a bit to simulate work
        logger.info("Simulating work with shared resources...")
        await asyncio.sleep(5)
        
        # 7. Release shared resources
        logger.info("Releasing shared resources...", allocation_id=allocation_id)
        released = await orchestrator.release_resources(allocation_id)
        if released:
            logger.info("Resources released successfully")
        else:
            logger.error("Failed to release resources")
            
    except Exception as e:
        logger.exception("An error occurred during resource sharing demonstration", error=str(e))
    finally:
        # 8. Clean up
        logger.info("Shutting down orchestrator...")
        await orchestrator.stop()
        await ssh_manager.close_all()

if __name__ == "__main__":
    asyncio.run(main())
