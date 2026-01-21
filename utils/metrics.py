from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry
import time
import logging

logger = logging.getLogger(__name__)

class Metrics:
    def __init__(self):
        self.registry = CollectorRegistry()
        
        # Counters
        self.tasks_submitted = Counter(
            'grid_tasks_submitted_total',
            'Total tasks submitted',
            ['task_type'],
            registry=self.registry
        )
        
        self.tasks_completed = Counter(
            'grid_tasks_completed_total',
            'Total tasks completed',
            ['task_type', 'status'],
            registry=self.registry
        )
        
        self.sync_operations = Counter(
            'grid_sync_operations_total',
            'Total sync operations',
            ['node', 'status'],
            registry=self.registry
        )
        
        # Histograms
        self.task_duration = Histogram(
            'grid_task_duration_seconds',
            'Task execution duration',
            ['task_type'],
            buckets=(0.1, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0),
            registry=self.registry
        )
        
        self.node_selection_time = Histogram(
            'grid_node_selection_seconds',
            'Time to select best node',
            buckets=(0.1, 0.5, 1.0, 2.0, 5.0),
            registry=self.registry
        )
        
        self.sync_duration = Histogram(
            'grid_sync_duration_seconds',
            'Code sync duration',
            ['node'],
            buckets=(0.5, 1.0, 2.0, 5.0, 10.0),
            registry=self.registry
        )
        
        # Gauges
        self.active_tasks = Gauge(
            'grid_active_tasks',
            'Currently active tasks',
            registry=self.registry
        )
        
        self.node_health_score = Gauge(
            'grid_node_health_score',
            'Node health score (lower is better)',
            ['node'],
            registry=self.registry
        )
    
    def record_task(self, task_type: str):
        """Record task submission"""
        self.tasks_submitted.labels(task_type=task_type).inc()
        self.active_tasks.inc()
    
    def record_task_complete(self, task_type: str, status: str = "success", duration: float = 0):
        """Record task completion"""
        self.tasks_completed.labels(task_type=task_type, status=status).inc()
        self.task_duration.labels(task_type=task_type).observe(duration)
        self.active_tasks.dec()
    
    def record_sync(self, node: str, status: str = "success"):
        """Record sync operation"""
        self.sync_operations.labels(node=node, status=status).inc()
    
    def record_node_health(self, node: str, score: float):
        """Record node health score"""
        self.node_health_score.labels(node=node).set(score)
    
    def export_prometheus(self) -> str:
        """Export metrics in Prometheus format"""
        from prometheus_client import generate_latest
        return generate_latest(self.registry).decode('utf-8')

# Global metrics instance
_metrics: Optional[Metrics] = None

def get_metrics() -> Metrics:
    global _metrics
    if _metrics is None:
        _metrics = Metrics()
    return _metrics
