"""Resource monitoring for intelligent resource sharing across the Ray cluster."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

import ray
import psutil
import structlog
from ray import nodes

from distributed_grid.config import ClusterConfig, NodeConfig

logger = structlog.get_logger(__name__)


class ResourceType(str, Enum):
    """Types of resources that can be shared."""
    CPU = "CPU"
    GPU = "GPU"
    MEMORY = "MEMORY"
    CUSTOM = "CUSTOM"


@dataclass
class ResourceSnapshot:
    """Snapshot of resource usage on a node."""
    node_id: str
    node_name: str
    timestamp: datetime
    cpu_count: int
    cpu_used: float
    cpu_available: float
    cpu_percent: float
    memory_total: int
    memory_used: int
    memory_available: int
    memory_percent: float
    gpu_count: int
    gpu_used: int
    gpu_available: int
    gpu_memory_total: int
    gpu_memory_used: int
    gpu_memory_available: int
    custom_resources: Dict[str, Tuple[int, int]] = field(default_factory=dict)
    
    @property
    def cpu_pressure(self) -> float:
        """Calculate CPU pressure score (0-1)."""
        return self.cpu_percent / 100.0
    
    @property
    def memory_pressure(self) -> float:
        """Calculate memory pressure score (0-1)."""
        return self.memory_percent / 100.0
    
    @property
    def gpu_pressure(self) -> float:
        """Calculate GPU pressure score (0-1)."""
        if self.gpu_count == 0:
            return 0.0
        return self.gpu_used / self.gpu_count
    
    @property
    def overall_pressure(self) -> float:
        """Calculate overall resource pressure score."""
        weights = {
            "cpu": 0.3,
            "memory": 0.3,
            "gpu": 0.4,
        }
        return (
            weights["cpu"] * self.cpu_pressure +
            weights["memory"] * self.memory_pressure +
            weights["gpu"] * self.gpu_pressure
        )


@dataclass
class ResourceTrend:
    """Trend analysis for resource usage."""
    resource_type: ResourceType
    current_value: float
    trend_5min: float  # Change over last 5 minutes
    trend_15min: float  # Change over last 15 minutes
    trend_1hour: float  # Change over last hour
    predicted_usage_5min: float
    predicted_usage_15min: float


class ResourceMetricsCollector:
    """Collects and analyzes resource metrics across the cluster."""
    
    def __init__(
        self,
        cluster_config: ClusterConfig,
        collection_interval: float = 10.0,
        history_size: int = 100,
    ):
        """Initialize the metrics collector."""
        self.cluster_config = cluster_config
        self.collection_interval = collection_interval
        self.history_size = history_size
        
        # Resource history for each node
        self._resource_history: Dict[str, List[ResourceSnapshot]] = {}
        self._latest_snapshot: Dict[str, ResourceSnapshot] = {}
        
        # Monitoring task
        self._monitoring_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Ray resources
        self._ray_cluster_resources = {}
        self._available_resources = {}
        
    async def start(self) -> None:
        """Start resource monitoring."""
        if self._running:
            return
            
        self._running = True
        logger.info("Starting resource metrics collector", interval=self.collection_interval)
        
        # Initialize Ray connection
        if not ray.is_initialized():
            ray.init(address="auto")
        
        # Start monitoring loop
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        # Initial collection
        await self._collect_all_metrics()
        
    async def stop(self) -> None:
        """Stop resource monitoring."""
        self._running = False
        
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
                
        logger.info("Resource metrics collector stopped")
        
    async def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await self._collect_all_metrics()
                await asyncio.sleep(self.collection_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in monitoring loop", error=str(e))
                await asyncio.sleep(5)
                
    async def _collect_all_metrics(self) -> None:
        """Collect metrics from all nodes in the cluster."""
        # Get Ray cluster resources
        self._ray_cluster_resources = ray.cluster_resources()
        self._available_resources = ray.available_resources()
        
        # Collect metrics from each node
        ray_nodes = ray.nodes()
        
        for node_config in self.cluster_config.nodes:
            node_id = node_config.name
            
            # Find corresponding Ray node
            ray_node = None
            for rn in ray_nodes:
                if rn.get("NodeManagerAddress") == node_config.host:
                    ray_node = rn
                    break
            
            # Collect resource snapshot
            snapshot = await self._collect_node_metrics(node_config, ray_node)
            
            # Store snapshot
            self._latest_snapshot[node_id] = snapshot
            
            # Update history
            if node_id not in self._resource_history:
                self._resource_history[node_id] = []
                
            self._resource_history[node_id].append(snapshot)
            
            # Trim history
            if len(self._resource_history[node_id]) > self.history_size:
                self._resource_history[node_id] = self._resource_history[node_id][-self.history_size:]
                
    async def _collect_node_metrics(
        self,
        node_config: NodeConfig,
        ray_node: Optional[Dict] = None,
    ) -> ResourceSnapshot:
        """Collect metrics from a specific node."""
        node_id = node_config.name
        
        # Get local metrics if this is the current node
        if node_config.host == "localhost" or node_config.host == ray.util.get_node_ip_address():
            return self._collect_local_metrics(node_config)
        
        # For remote nodes, we'd typically use SSH or Ray's metrics API
        # For now, we'll use Ray's node resources if available
        if ray_node:
            return self._collect_ray_node_metrics(node_config, ray_node)
        
        # Fallback to configured resources
        return self._get_configured_metrics(node_config)
        
    def _collect_local_metrics(self, node_config: NodeConfig) -> ResourceSnapshot:
        """Collect metrics from the local node."""
        # CPU metrics
        cpu_count = psutil.cpu_count()
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_used = cpu_count * (cpu_percent / 100.0)
        cpu_available = cpu_count - cpu_used
        
        # Memory metrics
        memory = psutil.virtual_memory()
        memory_total = memory.total
        memory_used = memory.used
        memory_available = memory.available
        memory_percent = memory.percent
        
        # GPU metrics (if nvidia-smi is available)
        gpu_count = node_config.gpu_count
        gpu_used = 0
        gpu_memory_total = 0
        gpu_memory_used = 0
        
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            if gpus:
                gpu_count = len(gpus)
                gpu_used = sum(1 for gpu in gpus if gpu.load > 0.1)
                gpu_memory_total = sum(gpu.memoryTotal for gpu in gpus)
                gpu_memory_used = sum(gpu.memoryUsed for gpu in gpus)
        except ImportError:
            # GPUtil not available, use basic GPU count
            pass
        
        gpu_available = gpu_count - gpu_used
        gpu_memory_available = gpu_memory_total - gpu_memory_used
        
        return ResourceSnapshot(
            node_id=node_config.name,
            node_name=node_config.name,
            timestamp=datetime.now(UTC),
            cpu_count=cpu_count,
            cpu_used=cpu_used,
            cpu_available=cpu_available,
            cpu_percent=cpu_percent,
            memory_total=memory_total,
            memory_used=memory_used,
            memory_available=memory_available,
            memory_percent=memory_percent,
            gpu_count=gpu_count,
            gpu_used=gpu_used,
            gpu_available=gpu_available,
            gpu_memory_total=gpu_memory_total,
            gpu_memory_used=gpu_memory_used,
            gpu_memory_available=gpu_memory_available,
        )
        
    def _collect_ray_node_metrics(
        self,
        node_config: NodeConfig,
        ray_node: Dict,
    ) -> ResourceSnapshot:
        """Collect metrics from Ray node information."""
        # Extract resource information from Ray node
        resources = ray_node.get("Resources", {})
        
        # CPU resources
        cpu_count = int(resources.get("CPU", 0))
        cpu_available = int(self._available_resources.get(f"node:{node_config.host}", 0).get("CPU", 0))
        cpu_used = cpu_count - cpu_available
        cpu_percent = (cpu_used / cpu_count * 100) if cpu_count > 0 else 0
        
        # Memory resources
        memory_total = node_config.memory_gb * 1024 * 1024 * 1024  # Convert GB to bytes
        memory_used = 0  # Ray doesn't easily expose memory usage per node
        memory_available = memory_total - memory_used
        memory_percent = (memory_used / memory_total * 100) if memory_total > 0 else 0
        
        # GPU resources
        gpu_count = int(resources.get("GPU", 0))
        gpu_available = int(self._available_resources.get(f"node:{node_config.host}", 0).get("GPU", 0))
        gpu_used = gpu_count - gpu_available
        
        # Estimate GPU memory based on configuration
        gpu_memory_total = gpu_count * 16 * 1024 * 1024 * 1024  # Assume 16GB per GPU
        gpu_memory_used = gpu_used * 8 * 1024 * 1024 * 1024  # Estimate 8GB used per active GPU
        gpu_memory_available = gpu_memory_total - gpu_memory_used
        
        return ResourceSnapshot(
            node_id=node_config.name,
            node_name=node_config.name,
            timestamp=datetime.now(UTC),
            cpu_count=cpu_count,
            cpu_used=cpu_used,
            cpu_available=cpu_available,
            cpu_percent=cpu_percent,
            memory_total=memory_total,
            memory_used=memory_used,
            memory_available=memory_available,
            memory_percent=memory_percent,
            gpu_count=gpu_count,
            gpu_used=gpu_used,
            gpu_available=gpu_available,
            gpu_memory_total=gpu_memory_total,
            gpu_memory_used=gpu_memory_used,
            gpu_memory_available=gpu_memory_available,
        )
        
    def _get_configured_metrics(self, node_config: NodeConfig) -> ResourceSnapshot:
        """Get metrics based on configuration when actual metrics unavailable."""
        cpu_count = node_config.cpu_count if hasattr(node_config, "cpu_count") else 4
        memory_total = node_config.memory_gb * 1024 * 1024 * 1024
        
        return ResourceSnapshot(
            node_id=node_config.name,
            node_name=node_config.name,
            timestamp=datetime.now(UTC),
            cpu_count=cpu_count,
            cpu_used=0,
            cpu_available=cpu_count,
            cpu_percent=0,
            memory_total=memory_total,
            memory_used=0,
            memory_available=memory_total,
            memory_percent=0,
            gpu_count=node_config.gpu_count,
            gpu_used=0,
            gpu_available=node_config.gpu_count,
            gpu_memory_total=node_config.gpu_count * 16 * 1024 * 1024 * 1024,
            gpu_memory_used=0,
            gpu_memory_available=node_config.gpu_count * 16 * 1024 * 1024 * 1024,
        )
        
    def get_latest_snapshot(self, node_id: str) -> Optional[ResourceSnapshot]:
        """Get the latest resource snapshot for a node."""
        return self._latest_snapshot.get(node_id)
        
    def get_all_latest_snapshots(self) -> Dict[str, ResourceSnapshot]:
        """Get the latest resource snapshots for all nodes."""
        return self._latest_snapshot.copy()
        
    def get_resource_trend(self, node_id: str, resource_type: ResourceType) -> Optional[ResourceTrend]:
        """Analyze resource usage trends for a node."""
        history = self._resource_history.get(node_id, [])
        if len(history) < 2:
            return None
            
        # Get current value
        latest = history[-1]
        if resource_type == ResourceType.CPU:
            current_value = latest.cpu_percent
        elif resource_type == ResourceType.MEMORY:
            current_value = latest.memory_percent
        elif resource_type == ResourceType.GPU:
            current_value = latest.gpu_pressure * 100
        else:
            return None
            
        # Calculate trends
        now = time.time()
        
        # 5-minute trend
        cutoff_5min = now - 300
        recent_5min = [s for s in history if s.timestamp.timestamp() > cutoff_5min]
        trend_5min = self._calculate_trend(recent_5min, resource_type)
        
        # 15-minute trend
        cutoff_15min = now - 900
        recent_15min = [s for s in history if s.timestamp.timestamp() > cutoff_15min]
        trend_15min = self._calculate_trend(recent_15min, resource_type)
        
        # 1-hour trend
        cutoff_1hour = now - 3600
        recent_1hour = [s for s in history if s.timestamp.timestamp() > cutoff_1hour]
        trend_1hour = self._calculate_trend(recent_1hour, resource_type)
        
        # Simple linear prediction
        predicted_5min = current_value + (trend_5min * 5)
        predicted_15min = current_value + (trend_15min * 15)
        
        return ResourceTrend(
            resource_type=resource_type,
            current_value=current_value,
            trend_5min=trend_5min,
            trend_15min=trend_15min,
            trend_1hour=trend_1hour,
            predicted_usage_5min=min(100, max(0, predicted_5min)),
            predicted_usage_15min=min(100, max(0, predicted_15min)),
        )
        
    def _calculate_trend(self, snapshots: List[ResourceSnapshot], resource_type: ResourceType) -> float:
        """Calculate trend as percentage change per minute."""
        if len(snapshots) < 2:
            return 0.0
            
        # Get values
        values = []
        for s in snapshots:
            if resource_type == ResourceType.CPU:
                values.append(s.cpu_percent)
            elif resource_type == ResourceType.MEMORY:
                values.append(s.memory_percent)
            elif resource_type == ResourceType.GPU:
                values.append(s.gpu_pressure * 100)
                
        if len(values) < 2:
            return 0.0
            
        # Simple linear regression
        n = len(values)
        x = list(range(n))
        
        x_mean = sum(x) / n
        y_mean = sum(values) / n
        
        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            return 0.0
            
        # Slope per sample, convert to per minute
        slope = numerator / denominator
        time_per_sample = self.collection_interval / 60.0  # Convert to minutes
        
        return slope * time_per_sample
        
    def get_cluster_summary(self) -> Dict[str, Any]:
        """Get a summary of cluster resources."""
        snapshots = self._latest_snapshot
        
        total_cpu = sum(s.cpu_count for s in snapshots.values())
        used_cpu = sum(s.cpu_used for s in snapshots.values())
        available_cpu = sum(s.cpu_available for s in snapshots.values())
        
        total_memory = sum(s.memory_total for s in snapshots.values())
        used_memory = sum(s.memory_used for s in snapshots.values())
        available_memory = sum(s.memory_available for s in snapshots.values())
        
        total_gpu = sum(s.gpu_count for s in snapshots.values())
        used_gpu = sum(s.gpu_used for s in snapshots.values())
        available_gpu = sum(s.gpu_available for s in snapshots.values())
        
        # Calculate pressure scores
        pressure_scores = {
            node_id: snapshot.overall_pressure
            for node_id, snapshot in snapshots.items()
        }
        
        # Find most and least loaded nodes
        if pressure_scores:
            most_loaded = max(pressure_scores.items(), key=lambda x: x[1])
            least_loaded = min(pressure_scores.items(), key=lambda x: x[1])
        else:
            most_loaded = least_loaded = (None, 0.0)
            
        return {
            "total_nodes": len(snapshots),
            "total_cpu": total_cpu,
            "used_cpu": used_cpu,
            "available_cpu": available_cpu,
            "cpu_utilization": (used_cpu / total_cpu * 100) if total_cpu > 0 else 0,
            "total_memory_gb": total_memory / (1024**3),
            "used_memory_gb": used_memory / (1024**3),
            "available_memory_gb": available_memory / (1024**3),
            "memory_utilization": (used_memory / total_memory * 100) if total_memory > 0 else 0,
            "total_gpu": total_gpu,
            "used_gpu": used_gpu,
            "available_gpu": available_gpu,
            "gpu_utilization": (used_gpu / total_gpu * 100) if total_gpu > 0 else 0,
            "node_pressure_scores": pressure_scores,
            "most_loaded_node": most_loaded,
            "least_loaded_node": least_loaded,
            "ray_cluster_resources": self._ray_cluster_resources,
            "ray_available_resources": self._available_resources,
        }
