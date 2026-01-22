"""Tests for utility functions."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from distributed_grid.utils import retry_async, RetryConfig, RetryError
from distributed_grid.utils.logging import setup_logging, get_logger
from distributed_grid.utils.metrics import MetricsCollector, MetricPoint


def test_setup_logging(tmp_path: Path) -> None:
    """Test logging setup."""
    log_file = tmp_path / "test.log"
    
    setup_logging(
        level="DEBUG",
        format_type="json",
        file_path=log_file,
    )
    
    logger = get_logger("test")
    logger.info("Test message")
    
    assert log_file.exists()


def test_get_logger() -> None:
    """Test getting a logger."""
    logger = get_logger("test")
    assert logger is not None
    assert logger.name == "test"


def test_metrics_collector_initialization() -> None:
    """Test metrics collector initialization."""
    collector = MetricsCollector(port=9000)
    assert collector.port == 9000
    assert len(collector._metrics) == 0


def test_metrics_collector_record_command() -> None:
    """Test recording command metrics."""
    collector = MetricsCollector()
    
    collector.record_command(
        node="test-node",
        status="success",
        duration=5.5,
    )
    
    # Check internal metrics
    points = collector.get_metrics("command_duration")
    assert len(points) == 1
    assert points[0].value == 5.5
    assert points[0].labels["node"] == "test-node"
    assert points[0].labels["status"] == "success"


def test_metrics_collector_update_node_status() -> None:
    """Test updating node status."""
    collector = MetricsCollector()
    
    collector.update_node_status("test-node", True)
    
    points = collector.get_metrics("node_status")
    assert len(points) == 1
    assert points[0].value == 1.0
    assert points[0].labels["node"] == "test-node"


def test_metrics_collector_update_gpu_utilization() -> None:
    """Test updating GPU utilization."""
    collector = MetricsCollector()
    
    collector.update_gpu_utilization("test-node", 0, 75.5)
    
    points = collector.get_metrics("gpu_utilization")
    assert len(points) == 1
    assert points[0].value == 75.5
    assert points[0].labels["node"] == "test-node"
    assert points[0].labels["gpu_id"] == "0"


def test_metrics_collector_get_average() -> None:
    """Test calculating average metrics."""
    collector = MetricsCollector()
    
    # Record some metrics
    for i in range(5):
        collector.record_command("test-node", "success", float(i + 1))
    
    avg = collector.get_average("command_duration")
    assert avg == 3.0  # Average of 1, 2, 3, 4, 5


def test_metrics_collector_get_average_empty() -> None:
    """Test calculating average with no metrics."""
    collector = MetricsCollector()
    
    avg = collector.get_average("non_existent")
    assert avg == 0.0


@pytest.mark.asyncio
async def test_retry_async_success() -> None:
    """Test successful retry on first attempt."""
    call_count = 0
    
    async def failing_func() -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("First attempt fails")
        return "success"
    
    config = RetryConfig(max_attempts=3)
    result = await retry_async(failing_func, config=config)
    
    assert result == "success"
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_async_exhausted() -> None:
    """Test retry when all attempts are exhausted."""
    async def always_failing_func() -> str:
        raise ValueError("Always fails")
    
    config = RetryConfig(max_attempts=3, base_delay=0.01)
    
    with pytest.raises(RetryError) as exc_info:
        await retry_async(always_failing_func, config=config)
    
    assert exc_info.value.attempts == 3
    assert isinstance(exc_info.value.last_exception, ValueError)


@pytest.mark.asyncio
async def test_retry_async_specific_exception() -> None:
    """Test retry only on specific exceptions."""
    async def func() -> str:
        raise TypeError("Not retried")
    
    config = RetryConfig(max_attempts=3, retry_on=(ValueError,))
    
    with pytest.raises(TypeError):
        await retry_async(func, config=config)


@pytest.mark.asyncio
async def test_retry_async_with_jitter() -> None:
    """Test retry with jitter enabled."""
    async def record_delay() -> str:
        raise ValueError("First attempt fails")
    
    config = RetryConfig(
        max_attempts=2,
        base_delay=0.1,
        jitter=True,
    )

    # Patch asyncio.sleep so we can validate the calculated delay without actually sleeping.
    with patch("distributed_grid.utils.retry.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        with pytest.raises(Exception):
            await retry_async(record_delay, config=config)

        # With jitter, delay should be between 0.05 and 0.1 seconds
        assert mock_sleep.await_count == 1
        delay = mock_sleep.await_args.args[0]
        assert 0.05 <= delay <= 0.1


def test_retry_config_defaults() -> None:
    """Test retry configuration defaults."""
    config = RetryConfig()
    
    assert config.max_attempts == 3
    assert config.base_delay == 1.0
    assert config.max_delay == 60.0
    assert config.exponential_base == 2.0
    assert config.jitter is True
    assert config.retry_on == (Exception,)


def test_metric_point_model() -> None:
    """Test MetricPoint model creation."""
    point = MetricPoint(
        timestamp=time.time(),
        value=42.0,
        labels={"node": "test", "type": "cpu"},
    )
    
    assert point.value == 42.0
    assert point.labels["node"] == "test"
    assert point.labels["type"] == "cpu"
