"""Integration module for intelligent resource sharing system."""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import timedelta

import ray
import structlog

from distributed_grid.config import ClusterConfig
from distributed_grid.core.ssh_manager import SSHManager
from distributed_grid.monitoring.resource_metrics import ResourceMetricsCollector, ResourceType
from distributed_grid.orchestration.resource_sharing_manager import (
    ResourceSharingManager,
    SharingPolicy,
)
from distributed_grid.orchestration.intelligent_scheduler import (
    IntelligentScheduler,
    SchedulingStrategy,
)
from distributed_grid.orchestration.enhanced_offloading_executor import (
    EnhancedOffloadingExecutor,
    OffloadingMode,
)
from distributed_grid.orchestration.offloading_detector import OffloadingDetector
from distributed_grid.orchestration.offloading_executor import OffloadingExecutor
from distributed_grid.orchestration.distributed_memory_pool import DistributedMemoryPool
from distributed_grid.orchestration.auto_offload_state import AutoOffloadState

logger = structlog.get_logger(__name__)


class ResourceSharingOrchestrator:
    """Orchestrates the intelligent resource sharing system."""
    
    def __init__(
        self,
        cluster_config: ClusterConfig,
        ssh_manager: SSHManager,
        ray_dashboard_address: str = "http://localhost:8265",
        boost_manager: Optional[Any] = None,
    ):
        """Initialize the orchestrator.
        
        Args:
            cluster_config: Cluster configuration
            ssh_manager: SSH manager for node access
            ray_dashboard_address: Ray dashboard address
            boost_manager: Optional resource boost manager for boost-aware scheduling
        """
        self.cluster_config = cluster_config
        self.ssh_manager = ssh_manager
        self.ray_dashboard_address = ray_dashboard_address
        self.boost_manager = boost_manager
        
        # Components
        self.metrics_collector: Optional[ResourceMetricsCollector] = None
        self.resource_sharing_manager: Optional[ResourceSharingManager] = None
        self.intelligent_scheduler: Optional[IntelligentScheduler] = None
        self.enhanced_executor: Optional[EnhancedOffloadingExecutor] = None
        self.legacy_executor: Optional[OffloadingExecutor] = None
        self.offloading_detector: Optional[OffloadingDetector] = None
        self.distributed_memory_pool: Optional[DistributedMemoryPool] = None
        
        # Configuration
        self.resource_sharing_enabled = cluster_config.resource_sharing.enabled
        
        # State
        self._initialized = False
        self._running = False
        self.memory_watchdog_active = True  # Enabled by default when resource sharing is on
        
        # Registry for objects that can be spilled to remote memory during pressure
        self._spillable_objects: Dict[str, Dict[str, Any]] = {}
        self._spilled_objects: Dict[str, str] = {}  # object_id -> block_id

        # Track PIDs being offloaded to prevent duplicate submissions
        self._offloading_pids: set = set()
        
    async def initialize(self) -> None:
        """Initialize all components."""
        if self._initialized:
            return
            
        logger.info("Initializing resource sharing orchestrator")
        
        # Initialize Ray if not already done
        if not ray.is_initialized():
            ray.init(address="auto")
            
        # Initialize components based on configuration
        if self.resource_sharing_enabled:
            await self._initialize_resource_sharing()
        else:
            await self._initialize_legacy()
            
        self._initialized = True
        logger.info("Resource sharing orchestrator initialized", sharing_enabled=self.resource_sharing_enabled)
        
    async def _initialize_resource_sharing(self) -> None:
        """Initialize resource sharing components."""
        config = self.cluster_config.resource_sharing
        
        # Initialize metrics collector
        self.metrics_collector = ResourceMetricsCollector(
            self.cluster_config,
            ssh_manager=self.ssh_manager,
            collection_interval=float(config.monitoring_interval_seconds),
        )
        # Register pressure callback for automatic mitigation
        self.metrics_collector.register_pressure_callback(self._handle_resource_pressure)

        # Check for auto-offload state and configure metrics collector
        try:
            auto_offload_state = AutoOffloadState()
            if auto_offload_state.enabled:
                # Enable head-only mode (only trigger offloads from head node)
                self.metrics_collector.set_head_only_mode(True)
                # Set pressure thresholds from auto-offload config
                memory_threshold = auto_offload_state.thresholds.get("memory", 70) / 100.0
                cpu_threshold = auto_offload_state.thresholds.get("cpu", 80) / 100.0
                self.metrics_collector.set_pressure_thresholds(
                    memory_threshold=memory_threshold,
                    cpu_threshold=cpu_threshold,
                )
                logger.info(
                    "Auto-offload enabled",
                    head_only_mode=True,
                    memory_threshold=f"{memory_threshold*100:.0f}%",
                    cpu_threshold=f"{cpu_threshold*100:.0f}%",
                )
        except Exception as e:
            logger.warning("Could not load auto-offload state", error=str(e))

        await self.metrics_collector.start()

        # Map string policy to enum
        policy_map = {
            "conservative": SharingPolicy.CONSERVATIVE,
            "balanced": SharingPolicy.BALANCED,
            "aggressive": SharingPolicy.AGGRESSIVE,
            "predictive": SharingPolicy.PREDICTIVE,
        }
        policy = policy_map.get(config.policy.lower(), SharingPolicy.BALANCED)
        
        # Initialize resource sharing manager
        self.resource_sharing_manager = ResourceSharingManager(
            self.cluster_config,
            self.metrics_collector,
            policy=policy,
            rebalance_interval=float(config.rebalance_interval_seconds),
            allocation_timeout=timedelta(minutes=config.allocation_timeout_minutes),
        )
        await self.resource_sharing_manager.start()
        
        # Initialize intelligent scheduler
        self.intelligent_scheduler = IntelligentScheduler(
            self.cluster_config,
            self.metrics_collector,
            self.resource_sharing_manager,
            boost_manager=self.boost_manager,
        )
        
        # Map string mode to enum
        mode_map = {
            "offload_only": OffloadingMode.OFFLOAD_ONLY,
            "share_and_offload": OffloadingMode.SHARE_AND_OFFLOAD,
            "dynamic_balancing": OffloadingMode.DYNAMIC_BALANCING,
        }
        mode = mode_map.get(config.mode.lower(), OffloadingMode.DYNAMIC_BALANCING)
        
        # Initialize enhanced executor
        self.enhanced_executor = EnhancedOffloadingExecutor(
            self.ssh_manager,
            self.cluster_config,
            self.ray_dashboard_address,
            mode=mode,
            metrics_collector=self.metrics_collector,
            boost_manager=self.boost_manager,
            resource_sharing_manager=self.resource_sharing_manager,
            intelligent_scheduler=self.intelligent_scheduler,
        )
        await self.enhanced_executor.initialize()
        
        # Initialize offloading detector
        self.offloading_detector = OffloadingDetector(
            self.ssh_manager,
            self.cluster_config
        )
        
        # Set up automatic offloading callback for boost manager if available
        if self.boost_manager and hasattr(self.boost_manager, 'on_boost_activated'):
            # Set callback to trigger automatic offloading when boost activates
            async def trigger_automatic_offloading(boost):
                """Trigger automatic offloading when a boost is activated on master node."""
                if boost.target_node == "gpu-master" and self.enhanced_executor and self.offloading_detector:
                    try:
                        logger.info(f"Boost {boost.boost_id} activated, triggering automatic offloading")
                        # Detect offloadable processes
                        recommendations = await self.offloading_detector.detect_offloading_candidates()
                        if recommendations:
                            logger.info(f"Found {len(recommendations)} processes to offload")
                            # Execute offloading for suitable processes
                            for rec in recommendations[:5]:  # Limit to 5 processes at a time
                                try:
                                    task_id = await self.enhanced_executor.execute_offloading(rec)
                                    logger.info(f"Offloaded process {rec.process.pid} to {rec.target_node}, task_id={task_id}")
                                except Exception as e:
                                    logger.warning(f"Failed to offload process {rec.process.pid}: {e}")
                        else:
                            logger.info("No offloadable processes found")
                    except Exception as e:
                        logger.error(f"Error in automatic offloading trigger: {e}")
            
            self.boost_manager.on_boost_activated = trigger_automatic_offloading
            logger.info("Automatic offloading callback configured for boost manager")
        
        # Initialize distributed memory pool
        self.distributed_memory_pool = DistributedMemoryPool(self.cluster_config)
        await self.distributed_memory_pool.initialize()
        logger.info("Distributed memory pool initialized")

    async def _handle_resource_pressure(self, node_id: str, resource_type: ResourceType, pressure: float) -> None:
        """Handle resource pressure events by triggering automatic mitigation."""
        if not self._running:
            return

        is_critical = pressure > 0.95
        log_level = "CRITICAL" if is_critical else "WARNING"
        
        logger.log(
            getattr(logging, log_level),
            "High resource pressure detected",
            node=node_id,
            resource=resource_type,
            pressure=f"{pressure*100:.1f}%",
            mode="EVACUATION" if is_critical else "MITIGATION"
        )

        # Only trigger mitigation for memory and CPU pressure
        if resource_type not in [ResourceType.MEMORY, ResourceType.CPU]:
            return

        # Attempt to offload processes from the pressured node
        try:
            # Discover all candidates
            recommendations = await self.offloading_detector.detect_offloading_candidates()
            
            # Filter recommendations for the pressured node
            node_recs = [r for r in recommendations if r.source_node == node_id]
            
            if not node_recs:
                logger.info("No offloading candidates found for pressured node", node=node_id)
                
                # If critical memory pressure and no process to offload, attempt object spilling
                if is_critical and resource_type == ResourceType.MEMORY:
                    await self._spill_registered_objects(node_id)
                return

            # In critical mode, be more aggressive
            limit = 5 if is_critical else 2

            # Filter out PIDs already being offloaded
            node_recs = [r for r in node_recs if r.process.pid not in self._offloading_pids]

            if not node_recs:
                logger.debug("All candidates already being offloaded", node=node_id)
                return

            # Execute recommendations
            for rec in node_recs[:limit]:
                # Skip if already being offloaded (double-check)
                if rec.process.pid in self._offloading_pids:
                    continue

                # Mark as being offloaded
                self._offloading_pids.add(rec.process.pid)

                logger.info(
                    "Mitigating pressure: Offloading process",
                    node=node_id,
                    pid=rec.process.pid,
                    name=rec.process.name,
                    target=rec.target_node,
                    critical=is_critical
                )
                try:
                    await self.execute_offloading(rec)
                finally:
                    # Remove from tracking after attempt (success or failure)
                    self._offloading_pids.discard(rec.process.pid)
                
            # If still critical after offloading processes, try spilling objects
            if is_critical and resource_type == ResourceType.MEMORY:
                await self._spill_registered_objects(node_id)
                
        except Exception as e:
            logger.error("Failed to execute automatic mitigation", node=node_id, error=str(e))

    def register_spillable_object(self, object_id: str, object_ref: ray.ObjectRef, node_id: str) -> None:
        """Register a Ray object as a candidate for emergency spilling."""
        self._spillable_objects[object_id] = {
            "ref": object_ref,
            "node_id": node_id,
            "registered_at": datetime.now(UTC)
        }
        logger.debug("Registered spillable object", object_id=object_id, node=node_id)

    def unregister_spillable_object(self, object_id: str) -> None:
        """Unregister an object from spill candidates."""
        if object_id in self._spillable_objects:
            del self._spillable_objects[object_id]
            logger.debug("Unregistered spillable object", object_id=object_id)

    async def _spill_registered_objects(self, node_id: str) -> int:
        """Emergency spill registered objects for a specific node to free memory."""
        if not self.distributed_memory_pool:
            return 0
            
        candidates = [
            (oid, info) for oid, info in self._spillable_objects.items()
            if info["node_id"] == node_id and oid not in self._spilled_objects
        ]
        
        if not candidates:
            return 0
            
        logger.warning("Emergency object spilling triggered", node=node_id, candidate_count=len(candidates))
        
        spilled_count = 0
        for object_id, info in candidates:
            try:
                block_id = await self.distributed_memory_pool.spill_object(info["ref"])
                if block_id:
                    self._spilled_objects[object_id] = block_id
                    spilled_count += 1
                    logger.info("Object spilled during emergency", object_id=object_id, block_id=block_id)
            except Exception as e:
                logger.error("Failed to spill object during emergency", object_id=object_id, error=str(e))
                
        return spilled_count
        
    async def evacuate_node(self, node_id: str) -> int:
        """Aggressively offload all possible processes from a node to mitigate emergencies."""
        if not self.offloading_detector:
            return 0
            
        logger.critical("Starting emergency node evacuation", node=node_id)
        
        # 1. Discover all candidates
        recommendations = await self.offloading_detector.detect_offloading_candidates()
        node_recs = [r for r in recommendations if r.source_node == node_id]
        
        if not node_recs:
            logger.info("No offloading candidates found for evacuation", node=node_id)
            return 0
            
        # 2. Execute all recommendations (no limit during evacuation)
        evacuated_count = 0
        for rec in node_recs:
            try:
                logger.info(
                    "Evacuating process",
                    node=node_id,
                    pid=rec.process.pid,
                    name=rec.process.name,
                    target=rec.target_node
                )
                await self.execute_offloading(rec)
                evacuated_count += 1
            except Exception as e:
                logger.error("Failed to evacuate process", pid=rec.process.pid, error=str(e))
                
        # 3. Emergency object spilling
        if self._spillable_objects:
            spilled = await self._spill_registered_objects(node_id)
            logger.info("Emergency objects spilled during evacuation", count=spilled)
            
        return evacuated_count

    async def _initialize_legacy(self) -> None:
        """Initialize legacy components without resource sharing."""
        self.legacy_executor = OffloadingExecutor(
            self.ssh_manager,
            self.cluster_config
        )
        
    async def stop(self) -> None:
        """Stop the orchestrator and all components."""
        if not self._running:
            return
            
        self._running = False
        
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        # Stop components in reverse order
        if self.offloading_detector:
            await self.offloading_detector.stop()
            
        if self.enhanced_executor:
            await self.enhanced_executor.stop()
            
        if self.resource_sharing_manager:
            await self.resource_sharing_manager.stop()
            
        if self.metrics_collector:
            await self.metrics_collector.stop()
            
        if self.distributed_memory_pool:
            await self.distributed_memory_pool.shutdown()
            
        logger.info("Resource sharing orchestrator stopped")
        
    async def run_forever(self) -> None:
        """Run the orchestrator continuously for background monitoring."""
        if not self._initialized:
            await self.initialize()
            
        self._running = True
        logger.info("Orchestrator entering continuous monitoring mode")
        try:
            while self._running:
                # The actual work is done in background tasks (metrics collector loop
                # and pressure callbacks), so we just wait here.
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Orchestrator continuous monitoring cancelled")
        finally:
            await self.stop()

    async def execute_offloading(self, recommendation, **kwargs) -> str:
        """Execute offloading using appropriate executor."""
        if self.resource_sharing_enabled and self.enhanced_executor:
            return await self.enhanced_executor.execute_offloading(recommendation, **kwargs)
        elif self.legacy_executor:
            return await self.legacy_executor.execute_offloading(recommendation, **kwargs)
        else:
            raise RuntimeError("No executor available")
            
    async def get_cluster_status(self) -> Dict[str, Any]:
        """Get comprehensive cluster status."""
        status = {
            "resource_sharing_enabled": self.resource_sharing_enabled,
            "initialized": self._initialized,
            "running": self._running,
            "memory_watchdog_active": self.memory_watchdog_active,
        }
        
        if self.resource_sharing_enabled:
            # Add metrics (nested format)
            if self.metrics_collector:
                status["metrics"] = self.metrics_collector.get_cluster_summary()
                status["node_snapshots"] = self.get_node_resource_snapshots()
                
            # Add resource sharing status
            if self.resource_sharing_manager:
                status["resource_sharing"] = self.resource_sharing_manager.get_resource_status()
                # Update the snapshots in resource_sharing to use the nested format
                if "node_snapshots" in status["resource_sharing"]:
                    status["resource_sharing"]["node_snapshots"] = status["node_snapshots"]
                
            # Add scheduler status
            if self.intelligent_scheduler:
                status["scheduler"] = self.intelligent_scheduler.get_scheduling_status()
                
            # Add executor statistics
            if self.enhanced_executor:
                status["executor"] = await self.enhanced_executor.get_enhanced_statistics()
                
            # Add distributed memory pool statistics
            if self.distributed_memory_pool:
                status["distributed_memory"] = await self.distributed_memory_pool.get_stats()
        else:
            # Legacy status
            if self.legacy_executor:
                status["executor"] = await self.legacy_executor.get_offloading_statistics()
                
        return status
        
    async def request_resources(
        self,
        node_id: str,
        resource_type: str,
        amount: float,
        priority: str = "normal",
        duration: Optional[timedelta] = None,
    ) -> str:
        """Request shared resources for a node."""
        if not self.resource_sharing_enabled or not self.resource_sharing_manager:
            raise RuntimeError("Resource sharing is not enabled")
            
        from distributed_grid.orchestration.resource_sharing_manager import (
            ResourceType,
            AllocationPriority,
        )
        
        resource_type_map = {
            "cpu": ResourceType.CPU,
            "gpu": ResourceType.GPU,
            "memory": ResourceType.MEMORY,
        }
        
        rt = resource_type_map.get(resource_type.lower())
        if not rt:
            raise ValueError(f"Invalid resource type: {resource_type}")
            
        priority_map = {
            "low": AllocationPriority.LOW,
            "normal": AllocationPriority.NORMAL,
            "high": AllocationPriority.HIGH,
            "critical": AllocationPriority.CRITICAL,
        }
        
        p = priority_map.get(priority.lower(), AllocationPriority.NORMAL)
        
        # Use provided duration or default to 30 mins
        d = duration if duration is not None else timedelta(minutes=30)
        
        return await self.resource_sharing_manager.request_resource(
            node_id=node_id,
            resource_type=rt,
            amount=amount,
            priority=p,
            duration=d,
        )
        
    async def release_resources(self, allocation_id: str) -> bool:
        """Release previously allocated resources."""
        if not self.resource_sharing_enabled or not self.resource_sharing_manager:
            raise RuntimeError("Resource sharing is not enabled")
            
        return await self.resource_sharing_manager.release_resource(allocation_id)
        
    async def detect_and_offload_processes(self) -> List[str]:
        """Detect processes that need offloading and execute it."""
        if not self.offloading_detector:
            logger.warning("Offloading detector not available")
            return []
            
        # Detect processes
        recommendations = await self.offloading_detector.detect_offloading_candidates()
        
        # Execute offloading
        task_ids = []
        for rec in recommendations:
            try:
                task_id = await self.execute_offloading(rec)
                task_ids.append(task_id)
                logger.info("Process offloaded", pid=rec.process.pid, task_id=task_id)
            except Exception as e:
                logger.error("Failed to offload process", pid=rec.process.pid, error=str(e))
                
        return task_ids
        
    def get_node_resource_snapshots(self) -> Dict[str, Dict[str, Any]]:
        """Get current resource snapshots for all nodes."""
        if not self.metrics_collector:
            return {}
            
        snapshots = self.metrics_collector.get_all_latest_snapshots()
        
        result = {}
        for node_id, snapshot in snapshots.items():
            result[node_id] = {
                "cpu": {
                    "total": snapshot.cpu_count,
                    "used": snapshot.cpu_used,
                    "available": snapshot.cpu_available,
                    "percent": snapshot.cpu_percent,
                },
                "memory": {
                    "total_gb": snapshot.memory_total / (1024**3),
                    "used_gb": snapshot.memory_used / (1024**3),
                    "available_gb": snapshot.memory_available / (1024**3),
                    "percent": snapshot.memory_percent,
                    "swap_total_gb": snapshot.swap_total / (1024**3),
                    "swap_used_gb": snapshot.swap_used / (1024**3),
                    "swap_percent": snapshot.swap_percent,
                },
                "gpu": {
                    "total": snapshot.gpu_count,
                    "used": snapshot.gpu_used,
                    "available": snapshot.gpu_available,
                    "memory_total_gb": snapshot.gpu_memory_total / (1024**3),
                    "memory_used_gb": snapshot.gpu_memory_used / (1024**3),
                    "memory_available_gb": snapshot.gpu_memory_available / (1024**3),
                },
                "pressure": {
                    "cpu": snapshot.cpu_pressure,
                    "memory": snapshot.memory_pressure,
                    "gpu": snapshot.gpu_pressure,
                    "overall": snapshot.overall_pressure,
                },
                "timestamp": snapshot.timestamp.isoformat(),
            }
            
        return result

    # Distributed Memory Pool API Methods
    
    async def allocate_distributed_memory(
        self,
        size_bytes: int,
        preferred_node: Optional[str] = None,
    ) -> Optional[str]:
        """Allocate distributed memory block.
        
        Args:
            size_bytes: Size in bytes to allocate
            preferred_node: Optional preferred node for allocation
            
        Returns:
            Block ID if successful, None otherwise
        """
        if not self.distributed_memory_pool:
            raise RuntimeError("Distributed memory pool is not initialized")
            
        return await self.distributed_memory_pool.allocate(size_bytes, preferred_node)
    
    async def deallocate_distributed_memory(self, block_id: str) -> bool:
        """Deallocate distributed memory block.
        
        Args:
            block_id: Block ID to deallocate
            
        Returns:
            True if successful, False otherwise
        """
        if not self.distributed_memory_pool:
            raise RuntimeError("Distributed memory pool is not initialized")
            
        return await self.distributed_memory_pool.deallocate(block_id)
    
    async def write_distributed_memory(
        self,
        block_id: str,
        data: bytes,
        offset: int = 0,
    ) -> bool:
        """Write data to distributed memory block.
        
        Args:
            block_id: Block ID to write to
            data: Data bytes to write
            offset: Offset in bytes to start writing
            
        Returns:
            True if successful, False otherwise
        """
        if not self.distributed_memory_pool:
            raise RuntimeError("Distributed memory pool is not initialized")
            
        return await self.distributed_memory_pool.write(block_id, data, offset)
    
    async def read_distributed_memory(
        self,
        block_id: str,
        size: int,
        offset: int = 0,
    ) -> Optional[bytes]:
        """Read data from distributed memory block.
        
        Args:
            block_id: Block ID to read from
            size: Number of bytes to read
            offset: Offset in bytes to start reading
            
        Returns:
            Data bytes if successful, None otherwise
        """
        if not self.distributed_memory_pool:
            raise RuntimeError("Distributed memory pool is not initialized")
            
        return await self.distributed_memory_pool.read(block_id, size, offset)
    
    async def get_distributed_memory_stats(self) -> Dict[str, Any]:
        """Get distributed memory pool statistics.
        
        Returns:
            Statistics dictionary with node-level details
        """
        if not self.distributed_memory_pool:
            raise RuntimeError("Distributed memory pool is not initialized")
            
        return await self.distributed_memory_pool.get_stats()
