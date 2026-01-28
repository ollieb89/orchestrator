from distributed_grid.monitoring.monitor_facade import MonitorFacade
from distributed_grid.monitoring.resource_metrics import ResourceSnapshot


def test_monitor_facade_normalizes_snapshot(monkeypatch, sample_cluster_config):
    facade = MonitorFacade(sample_cluster_config)
    snapshot = facade._normalize_snapshot(
        head_name="head",
        head_snapshot=ResourceSnapshot(
            node_id="head",
            node_name="head",
            timestamp=None,
            cpu_count=8,
            cpu_used=4,
            cpu_available=4,
            cpu_percent=50.0,
            memory_total=16,
            memory_used=8,
            memory_available=8,
            memory_percent=50.0,
            gpu_count=1,
            gpu_used=0,
            gpu_available=1,
            gpu_memory_total=8,
            gpu_memory_used=0,
            gpu_memory_available=8,
        ),
        queue_depth=3,
        node_snapshots={},
    )
    assert snapshot.queue_depth == 3
    assert snapshot.head.node_name == "head"
