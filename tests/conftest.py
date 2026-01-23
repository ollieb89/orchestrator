"""Pytest configuration and fixtures."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, Generator

import pytest
import yaml
from pydantic import ValidationError

from distributed_grid.config import ClusterConfig, NodeConfig
from distributed_grid.core import GridOrchestrator
from distributed_grid.utils.logging import setup_logging


def get_test_cluster_config() -> ClusterConfig:
    """Create a baseline cluster config for distributed memory tests."""
    return ClusterConfig(
        name="test-cluster",
        nodes=[
            NodeConfig(
                name="gpu-master",
                host="localhost",
                user="test",
                role="master",
                cpu_count=8,
                memory_gb=32,
                gpu_count=1,
                port=22,
                tags=["master", "gpu"],
            ),
            NodeConfig(
                name="gpu1",
                host="worker1",
                user="test",
                role="worker",
                cpu_count=6,
                memory_gb=16,
                gpu_count=1,
                port=22,
                tags=["worker", "gpu"],
            ),
            NodeConfig(
                name="gpu2",
                host="worker2",
                user="test",
                role="worker",
                cpu_count=4,
                memory_gb=8,
                gpu_count=0,
                port=22,
                tags=["worker"],
            ),
        ],
    )


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def setup_test_logging() -> None:
    """Setup logging for tests."""
    setup_logging(level="DEBUG", format_type="text")


@pytest.fixture
def sample_node_config() -> Dict[str, Any]:
    """Sample node configuration."""
    return {
        "name": "test-node-01",
        "host": "192.168.1.100",
        "port": 22,
        "user": "test-user",
        "gpu_count": 4,
        "memory_gb": 64,
        "tags": ["gpu", "cuda"],
    }


@pytest.fixture
def sample_cluster_config_data() -> Dict[str, Any]:
    """Sample cluster configuration data."""
    return {
        "name": "test-cluster",
        "nodes": [
            {
                "name": "test-node-01",
                "host": "192.168.1.100",
                "port": 22,
                "user": "test-user",
                "gpu_count": 4,
                "memory_gb": 64,
                "tags": ["gpu", "cuda"],
            },
            {
                "name": "test-node-02",
                "host": "192.168.1.101",
                "port": 22,
                "user": "test-user",
                "gpu_count": 8,
                "memory_gb": 128,
                "tags": ["gpu", "cuda", "tensor-cores"],
            },
        ],
        "execution": {
            "default_nodes": 2,
            "default_gpus_per_node": 1,
            "timeout_seconds": 1800,
            "retry_attempts": 2,
        },
        "logging": {
            "level": "DEBUG",
            "format": "text",
        },
    }


@pytest.fixture
def sample_cluster_config(
    sample_cluster_config_data: Dict[str, Any],
) -> ClusterConfig:
    """Sample cluster configuration object."""
    return ClusterConfig(**sample_cluster_config_data)


@pytest.fixture
def temp_config_file(
    tmp_path: Path,
    sample_cluster_config_data: Dict[str, Any],
) -> Path:
    """Create a temporary configuration file."""
    config_path = tmp_path / "test_config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(sample_cluster_config_data, f)
    return config_path


@pytest.fixture
def mock_orchestrator(sample_cluster_config: ClusterConfig) -> GridOrchestrator:
    """Create a mock orchestrator for testing."""
    return GridOrchestrator(sample_cluster_config)


@pytest.fixture
def mock_ssh_config() -> Dict[str, Any]:
    """Mock SSH configuration for testing."""
    return {
        "host": "localhost",
        "port": 22,
        "user": "test",
        "key_filename": "/tmp/test_key",
        "timeout": 30,
        "allow_agent": False,
        "look_for_keys": False,
    }


@pytest.fixture
async def initialized_orchestrator(
    mock_orchestrator: GridOrchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[GridOrchestrator, None, None]:
    """Create an initialized orchestrator with mocked connections."""
    # Mock the SSH manager to avoid actual connections
    async def mock_initialize() -> None:
        pass
    
    async def mock_check_all_nodes() -> list:
        from distributed_grid.core.health_checker import NodeHealth
        return [
            NodeHealth(is_online=True, load_average=[0.5, 0.3, 0.2]),
            NodeHealth(is_online=True, load_average=[0.8, 0.6, 0.4]),
        ]
    
    monkeypatch.setattr(mock_orchestrator.ssh_manager, "initialize", mock_initialize)
    monkeypatch.setattr(
        mock_orchestrator.health_checker,
        "check_all_nodes",
        mock_check_all_nodes,
    )
    
    await mock_orchestrator.initialize()
    yield mock_orchestrator
    await mock_orchestrator.shutdown()


@pytest.fixture
def invalid_config_data() -> Dict[str, Any]:
    """Invalid configuration data for testing validation."""
    return {
        "name": "",  # Empty name should fail
        "nodes": [],  # Empty nodes should fail
        "execution": {
            "default_nodes": -1,  # Negative should fail
            "timeout_seconds": 0,  # Zero should fail
        },
    }


class AsyncMock:
    """Helper class for mocking async functions."""
    
    def __init__(self, return_value: Any = None) -> None:
        self.return_value = return_value
        self.call_count = 0
        self.call_args = None
        self.call_kwargs = None
    
    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.call_count += 1
        self.call_args = args
        self.call_kwargs = kwargs
        return self.return_value


@pytest.fixture
def async_mock() -> type[AsyncMock]:
    """Fixture for AsyncMock class."""
    return AsyncMock
