from __future__ import annotations

import pytest
import asyncio

from distributed_grid.memory.distributed_memory_manager import DistributedMemoryManager
from tests.conftest import get_test_cluster_config


@pytest.mark.asyncio
async def test_store_and_retrieve() -> None:
    """Test basic store and retrieve operations."""
    manager = DistributedMemoryManager(get_test_cluster_config())
    await manager.initialize()
    
    # Store data
    test_data = {"message": "hello", "numbers": [1, 2, 3]}
    success = await manager.store("test_key", test_data)
    assert success, "Store operation should succeed"
    
    # Retrieve data
    retrieved = await manager.retrieve("test_key")
    assert retrieved == test_data, "Retrieved data should match stored data"


@pytest.mark.asyncio
async def test_store_large_dataset() -> None:
    """Test storing large datasets."""
    manager = DistributedMemoryManager(get_test_cluster_config())
    await manager.initialize()
    
    # Create large dataset (100MB)
    large_data = b"x" * (100 * 1024 * 1024)
    
    success = await manager.store("large_data", large_data)
    assert success, "Should be able to store large datasets"
    
    retrieved = await manager.retrieve("large_data")
    assert len(retrieved) == len(large_data), "Large data should be retrieved intact"


@pytest.mark.asyncio
async def test_nonexistent_key() -> None:
    """Test retrieving non-existent keys."""
    manager = DistributedMemoryManager(get_test_cluster_config())
    await manager.initialize()
    
    result = await manager.retrieve("nonexistent")
    assert result is None, "Non-existent keys should return None"


@pytest.mark.asyncio
async def test_delete_object() -> None:
    """Test object deletion."""
    manager = DistributedMemoryManager(get_test_cluster_config())
    await manager.initialize()
    
    # Store object first
    await manager.store("to_delete", "test_data")
    
    # Verify it exists
    assert await manager.retrieve("to_delete") is not None
    
    # Delete it
    success = await manager.delete("to_delete")
    assert success, "Delete should succeed"
    
    # Verify it's gone
    assert await manager.retrieve("to_delete") is None


@pytest.mark.asyncio
async def test_list_objects() -> None:
    """Test listing stored objects."""
    manager = DistributedMemoryManager(get_test_cluster_config())
    await manager.initialize()
    
    # Store multiple objects
    await manager.store("key1", "data1")
    await manager.store("key2", "data2")
    await manager.store("key3", "data3")
    
    objects = await manager.list_objects()
    assert len(objects) == 3, "Should list all stored objects"
    assert "key1" in objects
    assert "key2" in objects
    assert "key3" in objects


@pytest.mark.asyncio
async def test_get_stats() -> None:
    """Test statistics collection."""
    manager = DistributedMemoryManager(get_test_cluster_config())
    await manager.initialize()
    
    # Store some data
    await manager.store("small", "x" * 1000)  # ~1KB
    await manager.store("large", "x" * (10 * 1024 * 1024))  # ~10MB
    
    stats = await manager.get_stats()
    assert stats["total_objects"] == 2
    assert stats["total_mb"] > 10  # Should be > 10MB
    assert len(stats["objects"]) == 2
    
    # Check object details
    obj_names = {obj["key"] for obj in stats["objects"]}
    assert "small" in obj_names
    assert "large" in obj_names
