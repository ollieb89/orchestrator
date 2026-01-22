"""Resource sharing system for leveraging idle resources across nodes."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, UTC, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum

import structlog
from pydantic import BaseModel

from distributed_grid.core.ssh_manager import SSHManager
from distributed_grid.orchestration.resource_manager import ResourceUsage

logger = structlog.get_logger(__name__)


class ResourceType(str, Enum):
    """Types of resources that can be shared."""
    GPU = "gpu"
    MEMORY = "memory"
    CPU = "cpu"
    DISK = "disk"


@dataclass
class ResourceOffer:
    """An offer of resources from a worker node."""
    node_id: str
    resource_type: ResourceType
    amount: int
    available_until: datetime
    conditions: Dict[str, str]  # e.g., {"priority": "low", "max_runtime": "3600"}
    

@dataclass
class ResourceRequest:
    """A request for resources from the master node."""
    request_id: str
    resource_type: ResourceType
    amount: int
    priority: str  # "low", "medium", "high", "urgent"
    max_wait_time: int  # seconds
    job_id: Optional[str] = None
    preferred_nodes: Optional[List[str]] = None


@dataclass
class ResourceAllocation:
    """An allocation of resources to a job."""
    request_id: str
    node_id: str
    resource_type: ResourceType
    amount: int
    allocated_at: datetime
    expires_at: datetime


class ResourceSharingProtocol:
    """Protocol for communication between master and worker nodes for resource sharing."""
    
    def __init__(self, ssh_manager: SSHManager):
        """Initialize the protocol."""
        self.ssh_manager = ssh_manager
        self._worker_scripts_path = "~/.grid_worker"
        
    async def install_worker_agent(self, node_id: str) -> bool:
        """Install the worker agent on a node."""
        logger.info("Installing worker agent", node=node_id)

        worker_script = r"""import json
import psutil
import subprocess
from datetime import datetime, timezone


def get_gpu_info():
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.free,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
            gpus = []
            for line in lines:
                free, total, util = line.split(", ")
                gpus.append(
                    {
                        "memory_free_mb": int(free),
                        "memory_total_mb": int(total),
                        "utilization_percent": int(util),
                    }
                )
            return gpus
    except Exception:
        pass
    return []


def get_resource_status():
    cpu_percent = psutil.cpu_percent(interval=1)
    cpu_total = psutil.cpu_count() or 0
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cpu": {
            "percent": cpu_percent,
            "total_cores": cpu_total,
            "available_cores": psutil.cpu_count() - (psutil.cpu_count() * cpu_percent / 100),
        },
        "memory": {
            "total_gb": memory.total / (1024**3),
            "available_gb": memory.available / (1024**3),
            "percent": memory.percent,
        },
        "disk": {
            "total_gb": disk.total / (1024**3),
            "free_gb": disk.free / (1024**3),
        },
        "gpus": get_gpu_info(),
    }


def check_resource_offers(thresholds):
    status = get_resource_status()
    offers = []

    for i, gpu in enumerate(status["gpus"]):
        if gpu["utilization_percent"] < thresholds.get("gpu_utilization_max", 20):
            if gpu["memory_free_mb"] > thresholds.get("gpu_memory_min_mb", 1024):
                offers.append(
                    {
                        "resource_type": "gpu",
                        "amount": 1,
                        "gpu_id": i,
                        "memory_free_mb": gpu["memory_free_mb"],
                    }
                )

    if status["memory"]["percent"] < thresholds.get("memory_percent_max", 50):
        available_gb = status["memory"]["available_gb"] * 0.8
        if available_gb > thresholds.get("memory_min_gb", 2):
            offers.append(
                {
                    "resource_type": "memory",
                    "amount": int(available_gb),
                    "available_gb": available_gb,
                }
            )

    if status["cpu"]["percent"] < thresholds.get("cpu_percent_max", 30):
        available_cores = int(status["cpu"]["available_cores"] * 0.8)
        if available_cores > thresholds.get("cpu_min_cores", 1):
            offers.append(
                {
                    "resource_type": "cpu",
                    "amount": available_cores,
                    "available_cores": available_cores,
                }
            )

    return {
        "node_id": "__NODE_ID__",
        "timestamp": status["timestamp"],
        "offers": offers,
        "status": status,
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "check_offers":
        thresholds = {
            "gpu_utilization_max": 20,
            "gpu_memory_min_mb": 1024,
            "memory_percent_max": 50,
            "memory_min_gb": 2,
            "cpu_percent_max": 30,
            "cpu_min_cores": 1,
        }

        if len(sys.argv) > 2:
            thresholds.update(json.loads(sys.argv[2]))

        result = check_resource_offers(thresholds)
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps(get_resource_status(), indent=2))
"""

        worker_script = worker_script.replace("__NODE_ID__", node_id)

        install_script = (
            f"mkdir -p {self._worker_scripts_path}\n"
            f"cat > {self._worker_scripts_path}/resource_monitor.py << 'EOF'\n"
            f"{worker_script}\n"
            f"EOF\n"
            f"chmod +x {self._worker_scripts_path}/resource_monitor.py\n"
        )
        
        try:
            result = await self.ssh_manager.run_command(
                node_id,
                install_script,
                timeout=30,
            )
            if result.exit_status != 0:
                raise RuntimeError(result.stderr.strip() or "Worker agent install failed")
            logger.info("Worker agent installed successfully", node=node_id)
            return True
        except Exception as e:
            logger.error("Failed to install worker agent", node=node_id, error=str(e))
            return False
    
    async def check_node_resources(self, node_id: str, thresholds: Optional[Dict] = None) -> Optional[Dict]:
        """Check available resources on a node."""
        cmd = f"python3 {self._worker_scripts_path}/resource_monitor.py check_offers"
        
        if thresholds:
            cmd += f" '{json.dumps(thresholds)}'"
        
        try:
            result = await self.ssh_manager.run_command(
                node_id,
                cmd,
                timeout=10,
            )
            if result.exit_status != 0:
                logger.warning(
                    "Worker resource check failed",
                    node=node_id,
                    stderr=result.stderr.strip(),
                )
                return None
            return json.loads(result.stdout)
        except Exception as e:
            logger.error("Failed to check node resources", node=node_id, error=str(e))
            return None
    
    async def execute_remote_job(
        self,
        node_id: str,
        job_script: str,
        resources: Dict[str, int],
        work_dir: str = "~/grid_jobs"
    ) -> Tuple[bool, str]:
        """Execute a job on a remote node with allocated resources."""
        
        # Create work directory and job script
        setup_script = f"""
        mkdir -p {work_dir}
        cat > {work_dir}/job_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sh << 'EOF'
#!/bin/bash
set -e

# Resource allocation
{self._generate_resource_allocation_script(resources)}

# Job execution
{job_script}

EOF
        
        chmod +x {work_dir}/job_*.sh
        """
        
        try:
            # Setup
            setup_result = await self.ssh_manager.run_command(node_id, setup_script, timeout=10)
            if setup_result.exit_status != 0:
                raise RuntimeError(setup_result.stderr.strip() or "Remote job setup failed")
            
            # Execute
            job_cmd = f"cd {work_dir} && ./job_*.sh"
            result = await self.ssh_manager.run_command(node_id, job_cmd, timeout=3600)
            if result.exit_status != 0:
                raise RuntimeError(result.stderr.strip() or "Remote job execution failed")
            
            return True, result.stdout
        except Exception as e:
            return False, str(e)
    
    def _generate_resource_allocation_script(self, resources: Dict[str, int]) -> str:
        """Generate shell script for resource allocation."""
        script_parts = []
        
        if resources.get('gpu', 0) > 0:
            script_parts.append(f"export CUDA_VISIBLE_DEVICES={','.join(map(str, range(resources['gpu'])))}")
        
        if resources.get('cpu', 0) > 0:
            script_parts.append(f"taskset -c 0-$(({resources['cpu']} - 1))")
        
        return "\n".join(script_parts)


class ResourceSharingManager:
    """Manages resource sharing across the cluster."""
    
    def __init__(
        self,
        ssh_manager: SSHManager,
        check_interval: int = 60,
        offer_expiry: int = 300,  # 5 minutes
    ):
        """Initialize the resource sharing manager."""
        self.ssh_manager = ssh_manager
        self.protocol = ResourceSharingProtocol(ssh_manager)
        self.check_interval = check_interval
        self.offer_expiry = offer_expiry
        
        self._resource_offers: List[ResourceOffer] = []
        self._active_allocations: Dict[str, ResourceAllocation] = {}
        self._node_status: Dict[str, Dict] = {}
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Configuration for resource thresholds
        self.thresholds = {
            'gpu_utilization_max': 20,  # GPU utilization below this can be offered
            'gpu_memory_min_mb': 1024,  # Minimum free GPU memory
            'memory_percent_max': 50,   # Memory usage below this can be offered
            'memory_min_gb': 2,         # Minimum free memory in GB
            'cpu_percent_max': 30,      # CPU usage below this can be offered
            'cpu_min_cores': 1,         # Minimum free CPU cores
        }
    
    async def start(self) -> None:
        """Start the resource sharing manager."""
        logger.info("Starting resource sharing manager")
        self._running = True
        
        # Install worker agents on all nodes
        await self._install_worker_agents()

        # Perform an initial discovery so callers can see offers immediately
        await self._discover_resources()
        await self._cleanup_expired_offers()
        
        # Start monitoring task
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        
        logger.info("Resource sharing manager started")
    
    async def stop(self) -> None:
        """Stop the resource sharing manager."""
        logger.info("Stopping resource sharing manager")
        self._running = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Resource sharing manager stopped")
    
    async def request_resources(self, request: ResourceRequest) -> Optional[ResourceAllocation]:
        """Request resources from the cluster."""
        logger.info("Resource request received", request_id=request.request_id)
        
        # Find suitable offers
        suitable_offers = self._find_suitable_offers(request)
        
        if not suitable_offers:
            logger.warning("No suitable resources found", request_id=request.request_id)
            return None
        
        # Select the best offer
        best_offer = self._select_best_offer(suitable_offers, request)
        
        # Create allocation
        allocation = ResourceAllocation(
            request_id=request.request_id,
            node_id=best_offer.node_id,
            resource_type=best_offer.resource_type,
            amount=min(best_offer.amount, request.amount),
            allocated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(seconds=request.max_wait_time),
        )
        
        # Record allocation
        self._active_allocations[request.request_id] = allocation
        
        # Remove or update the offer
        self._update_offer_after_allocation(best_offer, allocation.amount)
        
        logger.info(
            "Resources allocated",
            request_id=request.request_id,
            node_id=allocation.node_id,
            amount=allocation.amount
        )
        
        return allocation
    
    async def release_resources(self, request_id: str) -> bool:
        """Release allocated resources."""
        if request_id not in self._active_allocations:
            logger.warning("Allocation not found", request_id=request_id)
            return False
        
        allocation = self._active_allocations.pop(request_id)
        
        logger.info(
            "Resources released",
            request_id=request_id,
            node_id=allocation.node_id,
            amount=allocation.amount
        )
        
        return True
    
    async def execute_on_shared_resources(
        self,
        request: ResourceRequest,
        job_script: str,
    ) -> Tuple[bool, str]:
        """Execute a job using shared resources."""
        # Request resources
        allocation = await self.request_resources(request)
        if not allocation:
            return False, "No resources available"
        
        try:
            # Execute the job
            success, output = await self.protocol.execute_remote_job(
                node_id=allocation.node_id,
                job_script=job_script,
                resources={allocation.resource_type.value: allocation.amount},
            )
            
            return success, output
        finally:
            # Always release resources
            await self.release_resources(request.request_id)
    
    async def _install_worker_agents(self) -> None:
        """Install worker agents on all nodes."""
        nodes = [n.name for n in self.ssh_manager.list_nodes()]
        
        tasks = []
        for node_id in nodes:
            task = asyncio.create_task(self.protocol.install_worker_agent(node_id))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for node_id, result in zip(nodes, results):
            if isinstance(result, Exception):
                logger.error("Failed to install agent", node=node_id, error=str(result))
            else:
                logger.info("Agent installed", node=node_id)
    
    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await self._discover_resources()
                await self._cleanup_expired_offers()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in monitor loop", error=str(e))
                await asyncio.sleep(5)
    
    async def _discover_resources(self) -> None:
        """Discover available resources from all nodes."""
        nodes = [n.name for n in self.ssh_manager.list_nodes()]
        
        tasks = []
        for node_id in nodes:
            task = asyncio.create_task(
                self.protocol.check_node_resources(node_id, self.thresholds)
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for node_id, result in zip(nodes, results):
            if isinstance(result, Exception):
                logger.error("Failed to check resources", node=node_id, error=str(result))
                continue
            
            if result and 'offers' in result:
                if isinstance(result.get("status"), dict):
                    self._node_status[node_id] = result["status"]
                await self._process_resource_offers(node_id, result['offers'])
    
    async def _process_resource_offers(self, node_id: str, offers: List[Dict]) -> None:
        """Process resource offers from a node."""
        status = self._node_status.get(node_id, {})

        for offer_data in offers:
            resource_type = ResourceType(offer_data['resource_type'])

            total: Optional[float] = None
            if resource_type == ResourceType.CPU:
                total = float(status.get("cpu", {}).get("total_cores") or 0)
            elif resource_type == ResourceType.MEMORY:
                total = float(status.get("memory", {}).get("total_gb") or 0.0)
            elif resource_type == ResourceType.GPU:
                # For GPU offers, keep total as gpu_count; per-GPU total mem can be included in conditions
                total = float(len(status.get("gpus", []) or []))
            
            offer = ResourceOffer(
                node_id=node_id,
                resource_type=resource_type,
                amount=offer_data['amount'],
                available_until=datetime.now(UTC) + timedelta(seconds=self.offer_expiry),
                conditions={
                    'gpu_id': str(offer_data.get('gpu_id', 'any')),
                    'memory_free_mb': str(offer_data.get('memory_free_mb', 0)),
                    'total': str(total) if total is not None else "0",
                }
            )

            # Enrich GPU offers with per-GPU total memory if available
            if resource_type == ResourceType.GPU and offer.conditions.get("gpu_id") not in (None, "any"):
                try:
                    gpu_id = int(offer.conditions["gpu_id"])
                    gpus = status.get("gpus", []) or []
                    if 0 <= gpu_id < len(gpus) and isinstance(gpus[gpu_id], dict):
                        offer.conditions["memory_total_mb"] = str(gpus[gpu_id].get("memory_total_mb", 0))
                except Exception:
                    pass
            
            # Check if we already have a similar offer
            existing = self._find_existing_offer(offer)
            if existing:
                # Update existing offer
                existing.available_until = offer.available_until
                existing.amount = offer.amount
                existing.conditions.update(offer.conditions)
            else:
                # Add new offer
                self._resource_offers.append(offer)
                logger.info(
                    "New resource offer",
                    node_id=node_id,
                    resource_type=resource_type,
                    amount=offer.amount
                )
    
    def _find_existing_offer(self, new_offer: ResourceOffer) -> Optional[ResourceOffer]:
        """Find an existing similar offer."""
        for offer in self._resource_offers:
            if (
                offer.node_id == new_offer.node_id
                and offer.resource_type == new_offer.resource_type
                and offer.conditions.get('gpu_id') == new_offer.conditions.get('gpu_id')
            ):
                return offer
        return None
    
    async def _cleanup_expired_offers(self) -> None:
        """Remove expired resource offers."""
        now = datetime.now(UTC)
        initial_count = len(self._resource_offers)
        
        self._resource_offers = [
            offer for offer in self._resource_offers
            if offer.available_until > now
        ]
        
        removed = initial_count - len(self._resource_offers)
        if removed > 0:
            logger.debug("Cleaned up expired offers", count=removed)
    
    def _find_suitable_offers(self, request: ResourceRequest) -> List[ResourceOffer]:
        """Find offers that match the request."""
        suitable = []
        
        for offer in self._resource_offers:
            if (
                offer.resource_type == request.resource_type
                and offer.amount >= request.amount
                and offer.available_until > datetime.now(UTC)
            ):
                # Check preferred nodes
                if request.preferred_nodes and offer.node_id not in request.preferred_nodes:
                    continue
                
                suitable.append(offer)
        
        return suitable
    
    def _select_best_offer(
        self,
        offers: List[ResourceOffer],
        request: ResourceRequest
    ) -> ResourceOffer:
        """Select the best offer from available options."""
        # Simple strategy: prefer node with most available resources
        # Could be enhanced with network latency, cost, etc.
        return max(offers, key=lambda o: o.amount)
    
    def _update_offer_after_allocation(self, offer: ResourceOffer, allocated_amount: int) -> None:
        """Update or remove an offer after allocation."""
        if offer.amount <= allocated_amount:
            # Remove the offer
            self._resource_offers.remove(offer)
        else:
            # Update the offer amount
            offer.amount -= allocated_amount
    
    def get_resource_offers(self) -> List[Dict]:
        """Get current resource offers."""
        return [
            {
                'node_id': offer.node_id,
                'resource_type': offer.resource_type.value,
                'amount': offer.amount,
                'total': offer.conditions.get('total', '0'),
                'available_until': offer.available_until.isoformat(),
                'conditions': offer.conditions,
            }
            for offer in self._resource_offers
        ]
    
    def get_active_allocations(self) -> List[Dict]:
        """Get active resource allocations."""
        return [
            {
                'request_id': allocation.request_id,
                'node_id': allocation.node_id,
                'resource_type': allocation.resource_type.value,
                'amount': allocation.amount,
                'allocated_at': allocation.allocated_at.isoformat(),
                'expires_at': allocation.expires_at.isoformat(),
            }
            for allocation in self._active_allocations.values()
        ]
