"""Metrics collector for gathering cluster metrics."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from prometheus_client import CollectorRegistry, Gauge, Counter, Histogram

from distributed_grid.schemas.node import Node


class MetricsCollector:
    """Collects and aggregates metrics from cluster nodes."""

    def __init__(self) -> None:
        """Initialize the metrics collector."""
        self.registry = CollectorRegistry()
        
        # Define metrics
        self.gpu_utilization = Gauge(
            "node_gpu_utilization",
            "GPU utilization percentage",
            ["node_id", "gpu_id"],
            registry=self.registry,
        )
        
        self.memory_utilization = Gauge(
            "node_memory_utilization",
            "Memory utilization percentage",
            ["node_id"],
            registry=self.registry,
        )
        
        self.cpu_utilization = Gauge(
            "node_cpu_utilization",
            "CPU utilization percentage",
            ["node_id"],
            registry=self.registry,
        )
        
        self.node_temperature = Gauge(
            "node_temperature",
            "Node temperature in Celsius",
            ["node_id"],
            registry=self.registry,
        )
        
        self.job_count = Counter(
            "cluster_job_count",
            "Number of jobs processed",
            ["cluster_id", "status"],
            registry=self.registry,
        )
        
        self.job_duration = Histogram(
            "job_duration_seconds",
            "Job execution duration",
            ["cluster_id"],
            registry=self.registry,
        )
        
        self._collecting = False
        self._metrics_history: Dict[str, List[Dict]] = {}

    async def start_collection(self, nodes: List[Node], interval_seconds: int = 30) -> None:
        """Start metrics collection."""
        self._collecting = True
        asyncio.create_task(self._collection_loop(nodes, interval_seconds))

    async def stop_collection(self) -> None:
        """Stop metrics collection."""
        self._collecting = False

    async def record_job_start(self, cluster_id: str, job_id: str) -> None:
        """Record the start of a job."""
        self.job_count.labels(cluster_id=cluster_id, status="started").inc()

    async def record_job_completion(
        self,
        cluster_id: str,
        job_id: str,
        duration_seconds: float,
        success: bool,
    ) -> None:
        """Record the completion of a job."""
        status = "completed" if success else "failed"
        self.job_count.labels(cluster_id=cluster_id, status=status).inc()
        self.job_duration.labels(cluster_id=cluster_id).observe(duration_seconds)

    async def get_metrics_history(
        self,
        node_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Dict]:
        """Get historical metrics for a node."""
        history = self._metrics_history.get(node_id, [])
        
        if start_time or end_time:
            filtered = []
            for point in history:
                timestamp = point["timestamp"]
                if start_time and timestamp < start_time:
                    continue
                if end_time and timestamp > end_time:
                    continue
                filtered.append(point)
            return filtered
        
        return history

    async def _collection_loop(self, nodes: List[Node], interval_seconds: int) -> None:
        """Main collection loop."""
        while self._collecting:
            # Collect from all nodes in parallel
            tasks = [
                self._collect_node_metrics(node)
                for node in nodes
            ]
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Wait for next collection
            await asyncio.sleep(interval_seconds)

    async def _collect_node_metrics(self, node: Node) -> None:
        """Collect metrics from a single node."""
        try:
            # TODO: Implement actual metrics collection
            # For now, simulate with random values
            import random
            
            metrics = {
                "timestamp": datetime.utcnow(),
                "gpu_utilization": random.uniform(0, 100),
                "memory_utilization": random.uniform(0, 100),
                "cpu_utilization": random.uniform(0, 100),
                "temperature": random.uniform(30, 80),
            }
            
            # Update Prometheus metrics
            self.memory_utilization.labels(node_id=node.id).set(metrics["memory_utilization"])
            self.cpu_utilization.labels(node_id=node.id).set(metrics["cpu_utilization"])
            self.node_temperature.labels(node_id=node.id).set(metrics["temperature"])
            
            # Store in history
            if node.id not in self._metrics_history:
                self._metrics_history[node.id] = []
            
            self._metrics_history[node.id].append(metrics)
            
            # Keep only last 1000 points
            if len(self._metrics_history[node.id]) > 1000:
                self._metrics_history[node.id] = self._metrics_history[node.id][-1000:]
                
        except Exception as e:
            # Log error but continue collecting from other nodes
            print(f"Failed to collect metrics from {node.id}: {e}")
