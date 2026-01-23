from __future__ import annotations

from datetime import datetime, UTC

import pytest

from distributed_grid.monitoring.resource_metrics import ResourceMetricsCollector, ResourceSnapshot
from distributed_grid.orchestration.enhanced_offloading_executor import (
    EnhancedOffloadingExecutor,
    OffloadingMode,
)
from distributed_grid.orchestration.offloading_detector import (
    OffloadingRecommendation,
    ProcessInfo,
    ProcessType,
)
from tests.conftest import get_test_cluster_config


def _make_snapshot(
    node_id: str,
    cpu_available: float,
    memory_total_gb: float,
    memory_used_gb: float,
    gpu_available: int,
) -> ResourceSnapshot:
    memory_total = int(memory_total_gb * 1024**3)
    memory_used = int(memory_used_gb * 1024**3)
    memory_available = memory_total - memory_used
    cpu_used = max(0.0, 16 - cpu_available)

    return ResourceSnapshot(
        node_id=node_id,
        node_name=node_id,
        timestamp=datetime.now(UTC),
        cpu_count=16,
        cpu_used=cpu_used,
        cpu_available=cpu_available,
        cpu_percent=(cpu_used / 16) * 100 if 16 else 0,
        memory_total=memory_total,
        memory_used=memory_used,
        memory_available=memory_available,
        memory_percent=(memory_used / memory_total) * 100 if memory_total else 0,
        gpu_count=1,
        gpu_used=max(0, 1 - gpu_available),
        gpu_available=gpu_available,
        gpu_memory_total=16 * 1024**3,
        gpu_memory_used=0,
        gpu_memory_available=16 * 1024**3,
    )


@pytest.mark.asyncio
async def test_memory_intensive_task_offloading() -> None:
    """Test that memory-intensive tasks trigger offloading from master."""
    cluster_config = get_test_cluster_config()
    metrics_collector = ResourceMetricsCollector(cluster_config)

    metrics_collector._latest_snapshot = {
        "gpu-master": _make_snapshot("gpu-master", 4.0, 32.0, 30.5, 1),
        "gpu1": _make_snapshot("gpu1", 6.0, 16.0, 4.0, 1),
        "gpu2": _make_snapshot("gpu2", 4.0, 8.0, 2.0, 0),
    }

    executor = EnhancedOffloadingExecutor(
        ssh_manager=None,
        cluster_config=cluster_config,
        mode=OffloadingMode.DYNAMIC_BALANCING,
        metrics_collector=metrics_collector,
    )

    process = ProcessInfo(
        pid=1234,
        name="memory-hungry",
        cmdline=["python", "task.py"],
        cpu_percent=20.0,
        memory_mb=6 * 1024,
        gpu_memory_mb=0,
        process_type=ProcessType.DATA_PROCESSING,
    )

    recommendation = OffloadingRecommendation(
        process=process,
        source_node="gpu-master",
        target_node="gpu1",
        confidence=0.9,
        reason="memory pressure",
        resource_match={},
        migration_complexity="low",
    )

    analysis = await executor._analyze_process_requirements(process)
    decision = await executor._make_offloading_decision(recommendation, analysis)

    assert decision.mode == OffloadingMode.OFFLOAD_ONLY
    assert decision.target_node == "gpu1"
