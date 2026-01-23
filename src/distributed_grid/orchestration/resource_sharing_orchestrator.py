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
from distributed_grid.monitoring.resource_metrics import ResourceMetricsCollector
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

logger = structlog.get_logger(__name__)


class ResourceSharingOrchestrator:
    """Orchestrates the intelligent resource sharing system."""
    
    def __init__(
        self,
        cluster_config: ClusterConfig,
        ssh_manager: SSHManager,
        ray_dashboard_address: str = "http://localhost:8265",
    ):
        """Initialize the orchestrator."""
        self.cluster_config = cluster_config
        self.ssh_manager = ssh_manager
        self.ray_dashboard_address = ray_dashboard_address
        
        # Components
        self.metrics_collector: Optional[ResourceMetricsCollector] = None
        self.resource_sharing_manager: Optional[ResourceSharingManager] = None
        self.intelligent_scheduler: Optional[IntelligentScheduler] = None
        self.enhanced_executor: Optional[EnhancedOffloadingExecutor] = None
        self.legacy_executor: Optional[OffloadingExecutor] = None
        self.offloading_detector: Optional[OffloadingDetector] = None
        
        # Configuration
        self.resource_sharing_enabled = cluster_config.resource_sharing.enabled
        
        # State
        self._initialized = False
        self._running = False
        
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
            resource_sharing_manager=self.resource_sharing_manager,
            intelligent_scheduler=self.intelligent_scheduler,
        )
        await self.enhanced_executor.initialize()
        
        # Initialize offloading detector
        self.offloading_detector = OffloadingDetector(
            self.ssh_manager,
            self.cluster_config
        )
        
    async def _initialize_legacy(self) -> None:
        """Initialize legacy components without resource sharing."""
        self.legacy_executor = OffloadingExecutor(
            self.ssh_manager,
            self.cluster_config,
            self.ray_dashboard_address,
        )
        await self.legacy_executor.initialize()
        
    async def start(self) -> None:
        """Start the orchestrator."""
        if not self._initialized:
            await self.initialize()
            
        if self._running:
            return
            
        self._running = True
        logger.info("Resource sharing orchestrator started")
        
    async def stop(self) -> None:
        """Stop the orchestrator."""
        if not self._running:
            return
            
        self._running = False
        
        # Stop components in reverse order
        if self.offloading_detector:
            await self.offloading_detector.stop()
            
        if self.enhanced_executor:
            # Executor doesn't have explicit stop, but we clean up resources
            pass
            
        if self.intelligent_scheduler:
            # Scheduler doesn't have explicit stop
            pass
            
        if self.resource_sharing_manager:
            await self.resource_sharing_manager.stop()
            
        if self.metrics_collector:
            await self.metrics_collector.stop()
            
        if self.legacy_executor:
            # Legacy executor doesn't have explicit stop
            pass
            
        logger.info("Resource sharing orchestrator stopped")
        
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
        }
        
        if self.resource_sharing_enabled:
            # Add metrics
            if self.metrics_collector:
                status["metrics"] = self.metrics_collector.get_cluster_summary()
                
            # Add resource sharing status
            if self.resource_sharing_manager:
                status["resource_sharing"] = self.resource_sharing_manager.get_resource_status()
                
            # Add scheduler status
            if self.intelligent_scheduler:
                status["scheduler"] = self.intelligent_scheduler.get_scheduling_status()
                
            # Add executor statistics
            if self.enhanced_executor:
                status["executor"] = await self.enhanced_executor.get_enhanced_statistics()
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
        duration_minutes: int = 30,
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
        
        return await self.resource_sharing_manager.request_resource(
            node_id=node_id,
            resource_type=rt,
            amount=amount,
            priority=p,
            duration=timedelta(minutes=duration_minutes),
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
