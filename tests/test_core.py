"""Tests for core orchestration components."""

from __future__ import annotations

import asyncio
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock

import pytest

from distributed_grid.core import GridOrchestrator
from distributed_grid.core.orchestrator import ClusterStatus, NodeStatus
from distributed_grid.core.health_checker import NodeHealth
from distributed_grid.core.executor import GridExecutor
from distributed_grid.core.ssh_manager import SSHManager


@pytest.mark.asyncio
async def test_orchestrator_initialization(
    mock_orchestrator: GridOrchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test orchestrator initialization."""
    # Mock the SSH manager
    mock_init = AsyncMock()
    monkeypatch.setattr(mock_orchestrator.ssh_manager, "initialize", mock_init)
    
    # Mock health checker
    mock_health = AsyncMock(return_value=[])
    monkeypatch.setattr(
        mock_orchestrator.health_checker,
        "check_all_nodes",
        mock_health,
    )
    
    await mock_orchestrator.initialize()
    
    assert mock_orchestrator._initialized
    mock_init.assert_called_once()
    mock_health.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_get_status(
    initialized_orchestrator: GridOrchestrator,
) -> None:
    """Test getting cluster status."""
    status = await initialized_orchestrator.get_status()
    
    assert status.name == "test-cluster"
    assert status.total_nodes == 2
    assert status.online_nodes == 2
    assert status.total_gpus == 12  # 4 + 8
    assert len(status.nodes) == 2
    
    for node in status.nodes:
        assert node.is_online
        assert node.last_check is not None


@pytest.mark.asyncio
async def test_orchestrator_run_command(
    initialized_orchestrator: GridOrchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test running a command on the cluster."""
    # Mock executor
    expected_results = {"test-node-01": "Success", "test-node-02": "Success"}
    mock_execute = AsyncMock(return_value=expected_results)
    monkeypatch.setattr(
        initialized_orchestrator.executor,
        "execute_on_nodes",
        mock_execute,
    )
    
    results = await initialized_orchestrator.run_command("echo test")
    
    assert results == expected_results
    mock_execute.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_run_command_specific_nodes(
    initialized_orchestrator: GridOrchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test running a command on specific nodes."""
    expected_results = {"test-node-01": "Success"}
    mock_execute = AsyncMock(return_value=expected_results)
    monkeypatch.setattr(
        initialized_orchestrator.executor,
        "execute_on_nodes",
        mock_execute,
    )
    
    results = await initialized_orchestrator.run_command(
        "echo test",
        node_names=["test-node-01"],
    )
    
    assert results == expected_results


@pytest.mark.asyncio
async def test_orchestrator_not_initialized(
    mock_orchestrator: GridOrchestrator,
) -> None:
    """Test that operations fail when orchestrator is not initialized."""
    with pytest.raises(RuntimeError, match="Orchestrator not initialized"):
        await mock_orchestrator.get_status()
    
    with pytest.raises(RuntimeError, match="Orchestrator not initialized"):
        await mock_orchestrator.run_command("echo test")


@pytest.mark.asyncio
async def test_orchestrator_shutdown(
    initialized_orchestrator: GridOrchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test orchestrator shutdown."""
    mock_close = AsyncMock()
    monkeypatch.setattr(
        initialized_orchestrator.ssh_manager,
        "close_all",
        mock_close,
    )
    
    await initialized_orchestrator.shutdown()
    
    assert not initialized_orchestrator._initialized
    mock_close.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_select_nodes(
    initialized_orchestrator: GridOrchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test node selection logic."""
    # Mock status with GPU utilization
    from distributed_grid.core.orchestrator import ClusterStatus, NodeStatus
    
    status = ClusterStatus(
        name="test-cluster",
        total_nodes=2,
        online_nodes=2,
        total_gpus=12,
        available_gpus=12,
        nodes=[
            NodeStatus(
                name="test-node-01",
                is_online=True,
                gpu_count=4,
                memory_gb=64,
                last_check=datetime.now(UTC),
                gpu_utilization=[0.8, 0.6, 0.4, 0.2],
            ),
            NodeStatus(
                name="test-node-02",
                is_online=True,
                gpu_count=8,
                memory_gb=128,
                last_check=datetime.now(UTC),
                gpu_utilization=[0.2, 0.1, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0],
            ),
        ],
        last_update=datetime.now(UTC),
    )
    
    mock_get_status = AsyncMock(return_value=status)
    monkeypatch.setattr(initialized_orchestrator, "get_status", mock_get_status)
    
    # Select 1 node with 2 GPUs
    nodes = await initialized_orchestrator._select_nodes(count=1, gpus_per_node=2)
    
    assert len(nodes) == 1
    # Should select node-02 due to lower GPU utilization
    assert nodes[0].name == "test-node-02"


@pytest.mark.asyncio
async def test_orchestrator_select_nodes_insufficient_gpus(
    initialized_orchestrator: GridOrchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test node selection when not enough GPUs are available."""
    # Mock status with nodes that don't have enough GPUs
    from distributed_grid.core.orchestrator import ClusterStatus, NodeStatus
    
    status = ClusterStatus(
        name="test-cluster",
        total_nodes=2,
        online_nodes=2,
        total_gpus=4,  # Total 4 GPUs
        available_gpus=4,
        nodes=[
            NodeStatus(
                name="test-node-01",
                is_online=True,
                gpu_count=2,
                memory_gb=64,
                last_check=datetime.now(UTC),
            ),
            NodeStatus(
                name="test-node-02",
                is_online=True,
                gpu_count=2,
                memory_gb=128,
                last_check=datetime.now(UTC),
            ),
        ],
        last_update=datetime.now(UTC),
    )
    
    mock_get_status = AsyncMock(return_value=status)
    monkeypatch.setattr(initialized_orchestrator, "get_status", mock_get_status)
    
    # Try to select 2 nodes with 4 GPUs each (should fail)
    with pytest.raises(RuntimeError, match="Not enough suitable nodes"):
        await initialized_orchestrator._select_nodes(count=2, gpus_per_node=4)


def test_node_status_model() -> None:
    """Test NodeStatus model creation."""
    status = NodeStatus(
        name="test-node",
        is_online=True,
        gpu_count=4,
        memory_gb=64,
        last_check=datetime.now(UTC),
        load_average=[0.5, 0.3, 0.2],
        gpu_utilization=[0.8, 0.6, 0.4, 0.2],
    )
    
    assert status.name == "test-node"
    assert status.is_online
    assert status.gpu_count == 4
    assert status.load_average == [0.5, 0.3, 0.2]
    assert status.gpu_utilization == [0.8, 0.6, 0.4, 0.2]


def test_cluster_status_model() -> None:
    """Test ClusterStatus model creation."""
    nodes = [
        NodeStatus(
            name="node-1",
            is_online=True,
            gpu_count=4,
            memory_gb=64,
            last_check=datetime.now(UTC),
        ),
        NodeStatus(
            name="node-2",
            is_online=False,
            gpu_count=8,
            memory_gb=128,
            last_check=datetime.now(UTC),
        ),
    ]
    
    status = ClusterStatus(
        name="test-cluster",
        total_nodes=2,
        online_nodes=1,
        total_gpus=12,
        available_gpus=4,
        nodes=nodes,
        last_update=datetime.now(UTC),
    )
    
    assert status.name == "test-cluster"
    assert status.total_nodes == 2
    assert status.online_nodes == 1
    assert status.total_gpus == 12
    assert len(status.nodes) == 2
