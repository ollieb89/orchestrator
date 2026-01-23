from __future__ import annotations

from datetime import datetime, UTC

import pytest

from distributed_grid.monitoring.resource_metrics import ResourceMetricsCollector, ResourceSnapshot
from distributed_grid.orchestration.enhanced_offloading_executor import EnhancedOffloadingExecutor
from tests.conftest import get_test_cluster_config


@pytest.mark.asyncio
async def test_memory_based_offloading_decision() -> None:
    cluster_config = get_test_cluster_config()
    metrics_collector = ResourceMetricsCollector(cluster_config)

    memory_total = int(30.4 * 1024**3)
    memory_used = int(28.0 * 1024**3)
    memory_available = memory_total - memory_used

    metrics_collector._latest_snapshot["gpu-master"] = ResourceSnapshot(
        node_id="gpu-master",
        node_name="gpu-master",
        timestamp=datetime.now(UTC),
        cpu_count=16,
        cpu_used=8,
        cpu_available=8,
        cpu_percent=50.0,
        memory_total=memory_total,
        memory_used=memory_used,
        memory_available=memory_available,
        memory_percent=(memory_used / memory_total) * 100,
        gpu_count=1,
        gpu_used=0,
        gpu_available=1,
        gpu_memory_total=16 * 1024**3,
        gpu_memory_used=0,
        gpu_memory_available=16 * 1024**3,
    )

    executor = EnhancedOffloadingExecutor(
        ssh_manager=None,
        cluster_config=cluster_config,
        metrics_collector=metrics_collector,
    )

    should_offload = await executor._should_offload_for_memory("gpu-master", 5.0)
    assert should_offload, "Large memory tasks should offload under pressure"

    metrics_collector._latest_snapshot["gpu-master"] = ResourceSnapshot(
        node_id="gpu-master",
        node_name="gpu-master",
        timestamp=datetime.now(UTC),
        cpu_count=16,
        cpu_used=2,
        cpu_available=14,
        cpu_percent=12.5,
        memory_total=memory_total,
        memory_used=int(8.0 * 1024**3),
        memory_available=memory_total - int(8.0 * 1024**3),
        memory_percent=(8.0 * 1024**3) / memory_total * 100,
        gpu_count=1,
        gpu_used=0,
        gpu_available=1,
        gpu_memory_total=16 * 1024**3,
        gpu_memory_used=0,
        gpu_memory_available=16 * 1024**3,
    )

    should_offload_small = await executor._should_offload_for_memory("gpu-master", 0.5)
    assert not should_offload_small, "Low memory tasks should stay local"
