"""Tests for ResourceBoostManager."""

import pytest
import asyncio
from datetime import datetime, UTC, timedelta
from unittest.mock import Mock, AsyncMock, patch

from distributed_grid.orchestration.resource_boost_manager import (
    ResourceBoostManager,
    ResourceBoost,
    ResourceBoostRequest,
)
from distributed_grid.monitoring.resource_metrics import (
    ResourceMetricsCollector,
    ResourceSnapshot,
    ResourceType,
)
from distributed_grid.config import ClusterConfig, NodeConfig
from distributed_grid.orchestration.resource_sharing_types import AllocationPriority


@pytest.fixture
def cluster_config():
    """Create a test cluster configuration."""
    nodes = [
        NodeConfig(
            name="gpu-master",
            host="gpu-master",
            user="ollie",
            gpu_count=1,
            memory_gb=32,
            role="master"
        ),
        NodeConfig(
            name="gpu1",
            host="gpu1",
            user="ob",
            gpu_count=1,
            memory_gb=16,
            role="worker"
        ),
        NodeConfig(
            name="gpu2",
            host="gpu2",
            user="ollie",
            gpu_count=1,
            memory_gb=32,
            role="worker"
        ),
    ]
    return ClusterConfig(name="test-cluster", nodes=nodes)


@pytest.fixture
def metrics_collector():
    """Create a mock metrics collector."""
    collector = Mock(spec=ResourceMetricsCollector)
    
    # Mock node snapshots
    snapshots = {
        "gpu-master": ResourceSnapshot(
            node_id="gpu-master",
            node_name="gpu-master",
            timestamp=datetime.now(UTC),
            cpu_count=16,
            cpu_used=8,
            cpu_available=8,
            cpu_percent=50.0,
            memory_total=32 * 1024**3,
            memory_used=16 * 1024**3,
            memory_available=16 * 1024**3,
            memory_percent=50.0,
            gpu_count=1,
            gpu_used=0,
            gpu_available=1,
            gpu_memory_total=24 * 1024**3,
            gpu_memory_used=0,
            gpu_memory_available=24 * 1024**3,
        ),
        "gpu1": ResourceSnapshot(
            node_id="gpu1",
            node_name="gpu1",
            timestamp=datetime.now(UTC),
            cpu_count=8,
            cpu_used=2,
            cpu_available=6,
            cpu_percent=25.0,
            memory_total=16 * 1024**3,
            memory_used=4 * 1024**3,
            memory_available=12 * 1024**3,
            memory_percent=25.0,
            gpu_count=1,
            gpu_used=0,
            gpu_available=1,
            gpu_memory_total=12 * 1024**3,
            gpu_memory_used=0,
            gpu_memory_available=12 * 1024**3,
        ),
        "gpu2": ResourceSnapshot(
            node_id="gpu2",
            node_name="gpu2",
            timestamp=datetime.now(UTC),
            cpu_count=16,
            cpu_used=4,
            cpu_available=12,
            cpu_percent=25.0,
            memory_total=32 * 1024**3,
            memory_used=8 * 1024**3,
            memory_available=24 * 1024**3,
            memory_percent=25.0,
            gpu_count=1,
            gpu_used=0,
            gpu_available=1,
            gpu_memory_total=24 * 1024**3,
            gpu_memory_used=0,
            gpu_memory_available=24 * 1024**3,
        ),
    }
    
    # Mock the get_all_latest_snapshots method
    collector.get_all_latest_snapshots.return_value = snapshots
    collector.get_latest_snapshot.side_effect = lambda node_id: snapshots.get(node_id)
    
    return collector


@pytest.fixture
def resource_sharing_manager():
    """Create a mock resource sharing manager."""
    manager = Mock()
    manager.request_resource = AsyncMock(return_value="allocation_123")
    return manager


@pytest.fixture
def boost_manager(cluster_config, metrics_collector, resource_sharing_manager):
    """Create a resource boost manager."""
    return ResourceBoostManager(
        cluster_config=cluster_config,
        metrics_collector=metrics_collector,
        resource_sharing_manager=resource_sharing_manager,
        default_boost_duration=timedelta(hours=1),
    )


@pytest.mark.asyncio
async def test_initialize(boost_manager):
    """Test boost manager initialization."""
    with patch('ray.is_initialized', return_value=False):
        with patch('ray.init') as mock_init:
            await boost_manager.initialize()
            mock_init.assert_called_once_with(address="auto")
    
    assert boost_manager._initialized


@pytest.mark.asyncio
async def test_request_cpu_boost(boost_manager):
    """Test requesting a CPU boost."""
    await boost_manager.initialize()
    
    request = ResourceBoostRequest(
        target_node="gpu-master",
        resource_type=ResourceType.CPU,
        amount=2.0,
        priority=AllocationPriority.HIGH,
        duration_seconds=1800,  # 30 minutes
    )
    
    # Check if mock is called correctly
    print(f"Mock RSM: {boost_manager.resource_sharing_manager}")
    print(f"Mock method: {boost_manager.resource_sharing_manager.request_resource}")
    
    boost_id = await boost_manager.request_boost(request)
    
    print(f"Boost ID returned: {boost_id}")
    print(f"Active boosts: {list(boost_manager._active_boosts.keys())}")
    
    assert boost_id is not None
    assert boost_id in boost_manager._active_boosts
    
    boost = boost_manager._active_boosts[boost_id]
    assert boost.target_node == "gpu-master"
    assert boost.resource_type == ResourceType.CPU
    assert boost.amount == 2.0
    assert boost.expires_at is not None


@pytest.mark.asyncio
async def test_request_gpu_boost(boost_manager):
    """Test requesting a GPU boost."""
    await boost_manager.initialize()
    
    request = ResourceBoostRequest(
        target_node="gpu-master",
        resource_type=ResourceType.GPU,
        amount=1.0,
        priority=AllocationPriority.CRITICAL,
    )
    
    boost_id = await boost_manager.request_boost(request)
    
    assert boost_id is not None
    boost = boost_manager._active_boosts[boost_id]
    assert boost.resource_type == ResourceType.GPU
    assert boost.amount == 1.0


@pytest.mark.asyncio
async def test_request_memory_boost(boost_manager):
    """Test requesting a memory boost."""
    await boost_manager.initialize()
    
    request = ResourceBoostRequest(
        target_node="gpu-master",
        resource_type=ResourceType.MEMORY,
        amount=4.0,  # 4GB
        priority=AllocationPriority.NORMAL,
    )
    
    boost_id = await boost_manager.request_boost(request)
    
    assert boost_id is not None
    boost = boost_manager._active_boosts[boost_id]
    assert boost.resource_type == ResourceType.MEMORY
    assert boost.amount == 4.0


@pytest.mark.asyncio
async def test_request_boost_with_preferred_source(boost_manager):
    """Test requesting a boost with a preferred source node."""
    await boost_manager.initialize()
    
    request = ResourceBoostRequest(
        target_node="gpu-master",
        resource_type=ResourceType.CPU,
        amount=2.0,
        preferred_source="gpu1",
    )
    
    boost_id = await boost_manager.request_boost(request)
    
    assert boost_id is not None
    boost = boost_manager._active_boosts[boost_id]
    assert boost.source_node == "gpu1"


@pytest.mark.asyncio
async def test_request_boost_insufficient_resources(boost_manager):
    """Test requesting a boost when no node has sufficient resources."""
    await boost_manager.initialize()
    
    # Request more CPUs than available
    request = ResourceBoostRequest(
        target_node="gpu-master",
        resource_type=ResourceType.CPU,
        amount=20.0,  # More than any node can provide
    )
    
    boost_id = await boost_manager.request_boost(request)
    
    assert boost_id is None


@pytest.mark.asyncio
async def test_release_boost(boost_manager):
    """Test releasing an active boost."""
    await boost_manager.initialize()
    
    # First create a boost
    request = ResourceBoostRequest(
        target_node="gpu-master",
        resource_type=ResourceType.CPU,
        amount=2.0,
    )
    
    boost_id = await boost_manager.request_boost(request)
    assert boost_id in boost_manager._active_boosts
    
    # Now release it
    success = await boost_manager.release_boost(boost_id)
    
    assert success
    assert boost_id not in boost_manager._active_boosts


@pytest.mark.asyncio
async def test_release_nonexistent_boost(boost_manager):
    """Test releasing a boost that doesn't exist."""
    await boost_manager.initialize()
    
    success = await boost_manager.release_boost("nonexistent_id")
    
    assert not success


@pytest.mark.asyncio
async def test_get_active_boosts(boost_manager):
    """Test getting list of active boosts."""
    await boost_manager.initialize()
    
    # Create multiple boosts
    requests = [
        ResourceBoostRequest("gpu-master", ResourceType.CPU, 2.0),
        ResourceBoostRequest("gpu-master", ResourceType.GPU, 1.0),
        ResourceBoostRequest("gpu1", ResourceType.MEMORY, 4.0),
    ]
    
    boost_ids = []
    for request in requests:
        boost_id = await boost_manager.request_boost(request)
        boost_ids.append(boost_id)
    
    # Get all boosts
    all_boosts = await boost_manager.get_active_boosts()
    assert len(all_boosts) == 3
    
    # Get boosts for specific node
    master_boosts = await boost_manager.get_active_boosts(target_node="gpu-master")
    assert len(master_boosts) == 2
    
    gpu1_boosts = await boost_manager.get_active_boosts(target_node="gpu1")
    assert len(gpu1_boosts) == 1


@pytest.mark.asyncio
async def test_get_boost_status(boost_manager):
    """Test getting boost status summary."""
    await boost_manager.initialize()
    
    # Create some boosts
    await boost_manager.request_boost(ResourceBoostRequest(
        "gpu-master", ResourceType.CPU, 2.0
    ))
    await boost_manager.request_boost(ResourceBoostRequest(
        "gpu-master", ResourceType.GPU, 1.0
    ))
    
    status = await boost_manager.get_boost_status()
    
    assert status["total_active_boosts"] == 2
    assert "CPU" in status["boosted_resources"]
    assert "GPU" in status["boosted_resources"]
    assert status["boosted_resources"]["CPU"] == 2.0
    assert status["boosted_resources"]["GPU"] == 1.0
    assert len(status["boosts"]) == 2


@pytest.mark.asyncio
async def test_cleanup_expired_boosts(boost_manager):
    """Test cleaning up expired boosts."""
    await boost_manager.initialize()
    
    # Create a boost with short expiration
    request = ResourceBoostRequest(
        target_node="gpu-master",
        resource_type=ResourceType.CPU,
        amount=2.0,
        duration_seconds=1,  # 1 second
    )
    
    boost_id = await boost_manager.request_boost(request)
    assert boost_id in boost_manager._active_boosts
    
    # Wait for expiration
    await asyncio.sleep(2)
    
    # Clean up expired boosts
    cleaned = await boost_manager.cleanup_expired_boosts()
    
    assert cleaned == 1
    assert boost_id not in boost_manager._active_boosts


@pytest.mark.asyncio
async def test_can_supply_resource_cpu(boost_manager):
    """Test resource availability check for CPU."""
    await boost_manager.initialize()
    
    # gpu1 has 6 CPUs available (8 total - 2 used)
    can_supply = await boost_manager._can_supply_resource("gpu1", ResourceType.CPU, 4.0)
    assert can_supply
    
    # But not 10 CPUs
    cannot_supply = await boost_manager._can_supply_resource("gpu1", ResourceType.CPU, 10.0)
    assert not cannot_supply


@pytest.mark.asyncio
async def test_can_supply_resource_memory(boost_manager):
    """Test resource availability check for memory."""
    await boost_manager.initialize()
    
    # gpu1 has 12GB available (16GB - 4GB used)
    can_supply = await boost_manager._can_supply_resource("gpu1", ResourceType.MEMORY, 8.0)
    assert can_supply
    
    # But not 16GB
    cannot_supply = await boost_manager._can_supply_resource("gpu1", ResourceType.MEMORY, 16.0)
    assert not cannot_supply


@pytest.mark.asyncio
async def test_can_supply_resource_gpu(boost_manager):
    """Test resource availability check for GPU."""
    await boost_manager.initialize()
    
    # gpu1 has 1 GPU available
    can_supply = await boost_manager._can_supply_resource("gpu1", ResourceType.GPU, 1.0)
    assert can_supply
    
    # But not 2 GPUs
    cannot_supply = await boost_manager._can_supply_resource("gpu1", ResourceType.GPU, 2.0)
    assert not cannot_supply


@pytest.mark.asyncio
async def test_find_source_node(boost_manager):
    """Test finding suitable source nodes."""
    await boost_manager.initialize()
    
    # Find source for CPU boost
    source = await boost_manager._find_source_node(
        "gpu-master", ResourceType.CPU, 2.0
    )
    assert source in ["gpu1", "gpu2"]
    
    # Find source with preference
    source = await boost_manager._find_source_node(
        "gpu-master", ResourceType.CPU, 2.0, preferred_source="gpu1"
    )
    assert source == "gpu1"


@patch('ray.experimental.set_resource')
@pytest.mark.asyncio
async def test_add_ray_resources(mock_set_resource, boost_manager):
    """Test adding boosted resources to Ray."""
    await boost_manager.initialize()
    
    boost = ResourceBoost(
        boost_id="test-boost-123",
        source_node="gpu1",
        target_node="gpu-master",
        resource_type=ResourceType.CPU,
        amount=2.0,
        allocated_at=datetime.now(UTC),
    )
    
    await boost_manager._add_ray_resources(boost)
    
    # Verify Ray resource was added
    mock_set_resource.assert_called_once()
    call_args = mock_set_resource.call_args[0]
    assert "boost_cpu_" in call_args[0]
    assert call_args[1] == 2.0


@patch('ray.experimental.set_resource')
@pytest.mark.asyncio
async def test_remove_ray_resources(mock_set_resource, boost_manager):
    """Test removing boosted resources from Ray."""
    await boost_manager.initialize()
    
    boost = ResourceBoost(
        boost_id="test-boost-123",
        source_node="gpu1",
        target_node="gpu-master",
        resource_type=ResourceType.CPU,
        amount=2.0,
        allocated_at=datetime.now(UTC),
    )
    
    # Simulate having added the resource
    boost_manager._boosted_resources["gpu-master"] = {
        "boost_cpu_test-boos": 2.0
    }
    
    await boost_manager._remove_ray_resources(boost)
    
    # Verify Ray resource was removed (set to 0)
    mock_set_resource.assert_called_with("boost_cpu_test-boos", 0)
