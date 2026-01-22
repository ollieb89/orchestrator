"""Metrics collection for the distributed grid."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, start_http_server


@dataclass
class MetricPoint:
    """A single metric data point."""
    timestamp: float
    value: float
    labels: Dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """Collects and manages metrics for the grid."""
    
    def __init__(self, port: int = 8000, registry: CollectorRegistry | None = None) -> None:
        """Initialize the metrics collector."""
        self.port = port
        self._registry = registry or CollectorRegistry(auto_describe=True)
        self._metrics: Dict[str, Deque[MetricPoint]] = defaultdict(lambda: deque(maxlen=1000))
        
        # Prometheus metrics
        self._command_counter = Counter(
            "grid_commands_total",
            "Total number of commands executed",
            ["node", "status"],
            registry=self._registry,
        )
        self._command_duration = Histogram(
            "grid_command_duration_seconds",
            "Command execution duration",
            ["node"],
            registry=self._registry,
        )
        self._node_status = Gauge(
            "grid_node_online",
            "Node online status",
            ["node"],
            registry=self._registry,
        )
        self._gpu_utilization = Gauge(
            "grid_gpu_utilization_percent",
            "GPU utilization percentage",
            ["node", "gpu_id"],
            registry=self._registry,
        )
        self._active_tasks = Gauge(
            "grid_active_tasks",
            "Number of active tasks",
            ["node"],
            registry=self._registry,
        )
    
    def start_server(self) -> None:
        """Start the Prometheus HTTP server."""
        start_http_server(self.port, registry=self._registry)
    
    def record_command(
        self,
        node: str,
        status: str,
        duration: float,
    ) -> None:
        """Record a command execution."""
        self._command_counter.labels(node=node, status=status).inc()
        self._command_duration.labels(node=node).observe(duration)
        
        # Store in internal metrics
        point = MetricPoint(
            timestamp=time.time(),
            value=duration,
            labels={"node": node, "status": status}
        )
        self._metrics["command_duration"].append(point)
    
    def update_node_status(self, node: str, online: bool) -> None:
        """Update node status."""
        self._node_status.labels(node=node).set(1 if online else 0)
        
        point = MetricPoint(
            timestamp=time.time(),
            value=1.0 if online else 0.0,
            labels={"node": node}
        )
        self._metrics["node_status"].append(point)
    
    def update_gpu_utilization(
        self,
        node: str,
        gpu_id: int,
        utilization: float,
    ) -> None:
        """Update GPU utilization."""
        self._gpu_utilization.labels(node=node, gpu_id=str(gpu_id)).set(utilization)
        
        point = MetricPoint(
            timestamp=time.time(),
            value=utilization,
            labels={"node": node, "gpu_id": str(gpu_id)}
        )
        self._metrics["gpu_utilization"].append(point)
    
    def update_active_tasks(self, node: str, count: int) -> None:
        """Update active task count."""
        self._active_tasks.labels(node=node).set(count)
        
        point = MetricPoint(
            timestamp=time.time(),
            value=float(count),
            labels={"node": node}
        )
        self._metrics["active_tasks"].append(point)
    
    def get_metrics(
        self,
        metric_name: str,
        since: float | None = None,
    ) -> List[MetricPoint]:
        """Get metrics for a specific name."""
        points = list(self._metrics.get(metric_name, []))
        
        if since is not None:
            points = [p for p in points if p.timestamp >= since]
        
        return points
    
    def get_average(
        self,
        metric_name: str,
        window_seconds: float = 300,
    ) -> float:
        """Get average value for a metric in the given window."""
        since = time.time() - window_seconds
        points = self.get_metrics(metric_name, since)
        
        if not points:
            return 0.0
        
        return sum(p.value for p in points) / len(points)


# Global metrics instance
_metrics: MetricsCollector | None = None


def get_metrics() -> MetricsCollector:
    """Get the global metrics instance."""
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics


def init_metrics(port: int = 8000) -> MetricsCollector:
    """Initialize the global metrics instance."""
    global _metrics
    _metrics = MetricsCollector(port)
    _metrics.start_server()
    return _metrics
