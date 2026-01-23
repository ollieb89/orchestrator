from __future__ import annotations

from datetime import datetime, UTC

import pytest

from distributed_grid.monitoring.resource_metrics import ResourceMetricsCollector, ResourceSnapshot
from tests.conftest import get_test_cluster_config


@pytest.mark.asyncio
async def test_memory_pressure_detection() -> None:
    collector = ResourceMetricsCollector(get_test_cluster_config())

    memory_total = int(30.4 * 1024**3)
    memory_used = int(28.0 * 1024**3)
    memory_available = memory_total - memory_used

    collector._latest_snapshot["gpu-master"] = ResourceSnapshot(
        node_id="gpu-master",
        node_name="gpu-master",
        timestamp=datetime.now(UTC),
        cpu_count=16,
        cpu_used=14,
        cpu_available=2,
        cpu_percent=87.5,
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

    pressure = collector.get_memory_pressure_score("gpu-master")
    assert pressure > 0.8, "High memory usage should result in high pressure score"
