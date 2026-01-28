from distributed_grid.orchestration.policy_engine import PolicyEngine
from distributed_grid.monitoring.resource_metrics import ResourceSnapshot


def test_policy_engine_thresholds_and_queue(monkeypatch):
    engine = PolicyEngine(
        cpu_threshold=0.8,
        memory_threshold=0.7,
        gpu_threshold=0.9,
        queue_threshold=5,
    )
    head = ResourceSnapshot(
        node_id="head",
        node_name="head",
        timestamp=None,
        cpu_count=8,
        cpu_used=7,
        cpu_available=1,
        cpu_percent=90.0,
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
    )
    decision = engine.evaluate(head, queue_depth=2)
    assert decision.should_offload is True
    assert "cpu" in decision.reasons
