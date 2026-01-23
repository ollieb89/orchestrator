"""Tests for distributed memory pool."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import numpy as np

from distributed_grid.orchestration.distributed_memory_pool import (
    DistributedMemoryPool,
    DistributedMemoryStore,
    MemoryBlock,
)
from distributed_grid.utils.memory_helpers import DistributedMemoryHelper
from distributed_grid.config import ClusterConfig, NodeConfig


@pytest.fixture
def cluster_config():
    """Create test cluster configuration."""
    return ClusterConfig(
        name="test-cluster",
        nodes=[
            NodeConfig(
                name="master",
                host="localhost",
                user="test",
                role="master",
                cpu_count=8,
                memory_gb=16,
                gpu_count=1,
            ),
            NodeConfig(
                name="worker1",
                host="worker1",
                user="test",
                role="worker",
                cpu_count=16,
                memory_gb=32,
                gpu_count=1,
            ),
            NodeConfig(
                name="worker2",
                host="worker2",
                user="test",
                role="worker",
                cpu_count=16,
                memory_gb=32,
                gpu_count=1,
            ),
        ],
    )


@pytest.fixture
def mock_ray():
    """Mock Ray for testing."""
    with patch('distributed_grid.orchestration.distributed_memory_pool.ray') as mock:
        mock.is_initialized.return_value = True
        yield mock


class TestDistributedMemoryStore:
    """Tests for DistributedMemoryStore actor."""
    
    def test_allocate(self):
        """Test memory allocation."""
        store = DistributedMemoryStore.__wrapped__(node_id="test-node")
        
        # Allocate memory
        success = store.allocate("block1", 1024)
        assert success is True
        assert "block1" in store.blocks
        assert len(store.blocks["block1"]) == 1024
    
    def test_write_read(self):
        """Test writing and reading data."""
        store = DistributedMemoryStore.__wrapped__(node_id="test-node")
        
        # Allocate and write
        store.allocate("block1", 1024)
        data = b"Hello, World!"
        success = store.write("block1", data, offset=0)
        assert success is True
        
        # Read back
        read_data = store.read("block1", len(data), offset=0)
        assert read_data == data
    
    def test_deallocate(self):
        """Test memory deallocation."""
        store = DistributedMemoryStore.__wrapped__(node_id="test-node")
        
        # Allocate and deallocate
        store.allocate("block1", 1024)
        assert "block1" in store.blocks
        
        success = store.deallocate("block1")
        assert success is True
        assert "block1" not in store.blocks
    
    def test_get_stats(self):
        """Test statistics retrieval."""
        store = DistributedMemoryStore.__wrapped__(node_id="test-node")
        
        # Allocate some blocks
        store.allocate("block1", 1024)
        store.allocate("block2", 2048)
        
        stats = store.get_stats()
        assert stats["node_id"] == "test-node"
        assert stats["blocks_count"] == 2
        assert stats["total_bytes"] == 3072
        assert stats["total_mb"] == pytest.approx(3072 / (1024**2))


class TestDistributedMemoryPool:
    """Tests for DistributedMemoryPool."""
    
    @pytest.mark.asyncio
    async def test_initialization(self, cluster_config, mock_ray):
        """Test pool initialization."""
        pool = DistributedMemoryPool(cluster_config)
        
        # Mock actor creation
        mock_actor = AsyncMock()
        mock_ray.remote.return_value.options.return_value.remote.return_value = mock_actor
        
        await pool.initialize()
        
        assert pool._initialized is True
        # Should create stores for worker nodes only
        assert len(pool.memory_stores) == 2
        assert "worker1" in pool.memory_stores
        assert "worker2" in pool.memory_stores
    
    @pytest.mark.asyncio
    async def test_allocate_success(self, cluster_config, mock_ray):
        """Test successful memory allocation."""
        pool = DistributedMemoryPool(cluster_config)
        
        # Mock actor
        mock_actor = AsyncMock()
        mock_actor.allocate.remote = AsyncMock(return_value=True)
        pool.memory_stores["worker1"] = mock_actor
        pool._initialized = True
        
        # Allocate memory
        block_id = await pool.allocate(1024**3, preferred_node="worker1")
        
        assert block_id is not None
        assert block_id.startswith("block_")
        assert "worker1" in block_id
        assert block_id in pool.blocks
        assert pool.blocks[block_id].size_bytes == 1024**3
    
    @pytest.mark.asyncio
    async def test_allocate_failure(self, cluster_config, mock_ray):
        """Test failed memory allocation."""
        pool = DistributedMemoryPool(cluster_config)
        
        # Mock actor that fails
        mock_actor = AsyncMock()
        mock_actor.allocate.remote = AsyncMock(return_value=False)
        pool.memory_stores["worker1"] = mock_actor
        pool._initialized = True
        
        # Try to allocate
        block_id = await pool.allocate(1024**3, preferred_node="worker1")
        
        assert block_id is None
    
    @pytest.mark.asyncio
    async def test_write_read(self, cluster_config, mock_ray):
        """Test writing and reading data."""
        pool = DistributedMemoryPool(cluster_config)
        
        # Mock actor
        mock_actor = AsyncMock()
        mock_actor.allocate.remote = AsyncMock(return_value=True)
        mock_actor.write.remote = AsyncMock(return_value=True)
        mock_actor.read.remote = AsyncMock(return_value=b"test data")
        pool.memory_stores["worker1"] = mock_actor
        pool._initialized = True
        
        # Allocate, write, and read
        block_id = await pool.allocate(1024, preferred_node="worker1")
        
        write_success = await pool.write(block_id, b"test data")
        assert write_success is True
        
        read_data = await pool.read(block_id, 9)
        assert read_data == b"test data"
    
    @pytest.mark.asyncio
    async def test_deallocate(self, cluster_config, mock_ray):
        """Test memory deallocation."""
        pool = DistributedMemoryPool(cluster_config)
        
        # Mock actor
        mock_actor = AsyncMock()
        mock_actor.allocate.remote = AsyncMock(return_value=True)
        mock_actor.deallocate.remote = AsyncMock(return_value=True)
        pool.memory_stores["worker1"] = mock_actor
        pool._initialized = True
        
        # Allocate and deallocate
        block_id = await pool.allocate(1024, preferred_node="worker1")
        assert block_id in pool.blocks
        
        success = await pool.deallocate(block_id)
        assert success is True
        assert block_id not in pool.blocks
    
    @pytest.mark.asyncio
    async def test_get_stats(self, cluster_config, mock_ray):
        """Test statistics retrieval."""
        pool = DistributedMemoryPool(cluster_config)
        
        # Mock actors
        mock_actor1 = AsyncMock()
        mock_actor1.get_stats.remote = AsyncMock(return_value={
            "node_id": "worker1",
            "blocks_count": 2,
            "total_mb": 10.0,
        })
        mock_actor2 = AsyncMock()
        mock_actor2.get_stats.remote = AsyncMock(return_value={
            "node_id": "worker2",
            "blocks_count": 1,
            "total_mb": 5.0,
        })
        
        pool.memory_stores["worker1"] = mock_actor1
        pool.memory_stores["worker2"] = mock_actor2
        pool._initialized = True
        pool.blocks = {"block1": Mock(), "block2": Mock(), "block3": Mock()}
        
        stats = await pool.get_stats()
        
        assert stats["total_blocks"] == 3
        assert "worker1" in stats["nodes"]
        assert "worker2" in stats["nodes"]
        assert stats["nodes"]["worker1"]["blocks_count"] == 2
        assert stats["nodes"]["worker2"]["total_mb"] == 5.0


class TestDistributedMemoryHelper:
    """Tests for DistributedMemoryHelper."""
    
    @pytest.mark.asyncio
    async def test_store_retrieve_object(self, cluster_config):
        """Test storing and retrieving Python objects."""
        # Create mock pool
        mock_pool = AsyncMock()
        mock_pool.allocate = AsyncMock(return_value="block_test")
        mock_pool.write = AsyncMock(return_value=True)
        mock_pool.read = AsyncMock()
        mock_pool.blocks = {}
        
        helper = DistributedMemoryHelper(mock_pool)
        
        # Store object
        test_obj = {"key": "value", "number": 42}
        block_id = await helper.store_object(test_obj, preferred_node="worker1")
        
        assert block_id == "block_test"
        mock_pool.allocate.assert_called_once()
        mock_pool.write.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_store_retrieve_numpy_array(self, cluster_config):
        """Test storing and retrieving NumPy arrays."""
        # Create mock pool
        mock_pool = AsyncMock()
        mock_pool.allocate = AsyncMock(return_value="block_array")
        mock_pool.write = AsyncMock(return_value=True)
        mock_pool.blocks = {}
        
        helper = DistributedMemoryHelper(mock_pool)
        
        # Store array
        test_array = np.random.rand(100, 100)
        block_id = await helper.store_numpy_array(test_array, preferred_node="worker1")
        
        assert block_id == "block_array"
        mock_pool.allocate.assert_called_once()
        # Should write metadata size, metadata, and array data
        assert mock_pool.write.call_count == 3
    
    @pytest.mark.asyncio
    async def test_cache_operations(self, cluster_config):
        """Test cache operations."""
        # Create mock pool
        mock_pool = AsyncMock()
        mock_pool.allocate = AsyncMock(return_value="cache_test_key")
        mock_pool.write = AsyncMock(return_value=True)
        mock_pool.deallocate = AsyncMock(return_value=True)
        mock_pool.blocks = {}
        
        helper = DistributedMemoryHelper(mock_pool)
        
        # Cache data
        success = await helper.cache_large_data("test_key", {"data": "value"})
        assert success is True
        
        # Clear cache
        mock_pool.blocks = {"cache_test_key": Mock()}
        success = await helper.clear_cache("test_key")
        assert success is True
    
    @pytest.mark.asyncio
    async def test_memory_usage_summary(self, cluster_config):
        """Test memory usage summary."""
        # Create mock pool
        mock_pool = AsyncMock()
        mock_pool.get_stats = AsyncMock(return_value={
            "total_blocks": 5,
            "nodes": {
                "worker1": {"blocks_count": 3, "total_mb": 150.0},
                "worker2": {"blocks_count": 2, "total_mb": 100.0},
            }
        })
        
        helper = DistributedMemoryHelper(mock_pool)
        
        summary = await helper.get_memory_usage_summary()
        
        assert summary["total_blocks"] == 5
        assert summary["total_memory_mb"] == 250.0
        assert "worker1" in summary["nodes"]
        assert summary["nodes"]["worker1"]["memory_mb"] == 150.0


@pytest.mark.asyncio
async def test_integration_scenario(cluster_config, mock_ray):
    """Test end-to-end integration scenario."""
    # Create pool
    pool = DistributedMemoryPool(cluster_config)
    
    # Mock actors
    mock_actor = AsyncMock()
    mock_actor.allocate.remote = AsyncMock(return_value=True)
    mock_actor.write.remote = AsyncMock(return_value=True)
    mock_actor.read.remote = AsyncMock(return_value=b"integration test data")
    mock_actor.deallocate.remote = AsyncMock(return_value=True)
    mock_actor.get_stats.remote = AsyncMock(return_value={
        "node_id": "worker1",
        "blocks_count": 1,
        "total_mb": 0.02,
    })
    
    pool.memory_stores["worker1"] = mock_actor
    pool._initialized = True
    
    # Allocate memory
    block_id = await pool.allocate(1024, preferred_node="worker1")
    assert block_id is not None
    
    # Write data
    success = await pool.write(block_id, b"integration test data")
    assert success is True
    
    # Read data
    data = await pool.read(block_id, 21)
    assert data == b"integration test data"
    
    # Get stats
    stats = await pool.get_stats()
    assert stats["total_blocks"] == 1
    
    # Deallocate
    success = await pool.deallocate(block_id)
    assert success is True
    assert block_id not in pool.blocks
