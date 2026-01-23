"""Tests for Resource Boost Manager persistence functionality."""

import pytest
import asyncio
from datetime import datetime, UTC, timedelta
from pathlib import Path
import tempfile
import shutil
import json

from distributed_grid.orchestration.resource_boost_persistence import ResourceBoostPersistence
from distributed_grid.orchestration.resource_boost_manager import (
    ResourceBoostManager,
    ResourceBoost,
    ResourceBoostRequest,
)
from distributed_grid.monitoring.resource_metrics import ResourceType
from distributed_grid.orchestration.resource_sharing_types import AllocationPriority


class TestResourceBoostPersistence:
    """Test the persistence layer for resource boosts."""
    
    def test_persistence_initialization(self):
        """Test that persistence initializes correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persistence = ResourceBoostPersistence(data_dir=tmpdir)
            
            # Check that directory was created
            assert Path(tmpdir).exists()
            assert persistence.boosts_file.exists() == False
            
            # Check file info
            info = persistence.get_file_info()
            assert info["exists"] == False
            assert tmpdir in info["path"]
    
    def test_save_and_load_boosts(self):
        """Test saving and loading boosts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persistence = ResourceBoostPersistence(data_dir=tmpdir)
            
            # Create test boosts
            now = datetime.now(UTC)
            boosts = [
                {
                    "boost_id": "test-boost-1",
                    "source_node": "gpu1",
                    "target_node": "gpu-master",
                    "resource_type": ResourceType.CPU,
                    "amount": 2.0,
                    "allocated_at": now,
                    "expires_at": now + timedelta(hours=1),
                    "is_active": True
                },
                {
                    "boost_id": "test-boost-2",
                    "source_node": "gpu2",
                    "target_node": "gpu-master",
                    "resource_type": ResourceType.GPU,
                    "amount": 1.0,
                    "allocated_at": now,
                    "expires_at": now + timedelta(hours=2),
                    "is_active": True
                }
            ]
            
            # Save boosts
            persistence.save_boosts(boosts)
            
            # Check file exists
            assert persistence.boosts_file.exists()
            
            # Load boosts
            loaded_boosts = persistence.load_boosts()
            
            assert len(loaded_boosts) == 2
            assert loaded_boosts[0]["boost_id"] == "test-boost-1"
            assert loaded_boosts[0]["resource_type"] == ResourceType.CPU
            assert loaded_boosts[1]["resource_type"] == ResourceType.GPU
            assert isinstance(loaded_boosts[0]["allocated_at"], datetime)
            assert isinstance(loaded_boosts[0]["expires_at"], datetime)
    
    def test_load_empty_boosts(self):
        """Test loading when no file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persistence = ResourceBoostPersistence(data_dir=tmpdir)
            
            # Load should return empty list
            boosts = persistence.load_boosts()
            assert boosts == []
    
    def test_clear_boosts(self):
        """Test clearing persisted boosts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persistence = ResourceBoostPersistence(data_dir=tmpdir)
            
            # Save some boosts
            boosts = [{"boost_id": "test", "is_active": True}]
            persistence.save_boosts(boosts)
            
            # Verify file exists
            assert persistence.boosts_file.exists()
            
            # Clear boosts
            persistence.clear_boosts()
            
            # File should be gone
            assert persistence.boosts_file.exists() == False
    
    def test_handle_invalid_json(self):
        """Test handling of invalid JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persistence = ResourceBoostPersistence(data_dir=tmpdir)
            
            # Write invalid JSON
            with open(persistence.boosts_file, 'w') as f:
                f.write("invalid json content")
            
            # Load should return empty list and not crash
            boosts = persistence.load_boosts()
            assert boosts == []


class TestResourceBoostManagerPersistence:
    """Test ResourceBoostManager with persistence."""
    
    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies for ResourceBoostManager."""
        from unittest.mock import Mock, AsyncMock
        
        # Mock cluster config
        mock_config = Mock()
        mock_config.nodes = [
            Mock(name="gpu-master", role="master"),
            Mock(name="gpu1", role="worker"),
            Mock(name="gpu2", role="worker")
        ]
        
        # Mock metrics collector
        mock_metrics = Mock()
        mock_metrics.get_all_latest_snapshots.return_value = {
            "gpu1": Mock(cpu_available=10.0, gpu_available=1.0, memory_available=8*1024**3),
            "gpu2": Mock(cpu_available=10.0, gpu_available=1.0, memory_available=8*1024**3)
        }
        
        # Mock resource sharing manager
        mock_sharing = Mock()
        mock_sharing.request_resource = AsyncMock(return_value="allocation-123")
        
        return mock_config, mock_metrics, mock_sharing
    
    @pytest.mark.asyncio
    async def test_persistence_loads_on_initialization(self, mock_dependencies):
        """Test that boosts are loaded when manager is initialized."""
        config, metrics, sharing = mock_dependencies
        
        with tempfile.TemporaryDirectory() as tmpdir:
            persistence = ResourceBoostPersistence(data_dir=tmpdir)
            
            # Save an existing boost
            existing_boost = {
                "boost_id": "existing-boost",
                "source_node": "gpu1",
                "target_node": "gpu-master",
                "resource_type": ResourceType.CPU,
                "amount": 2.0,
                "allocated_at": datetime.now(UTC) - timedelta(minutes=5),
                "expires_at": datetime.now(UTC) + timedelta(hours=1),
                "is_active": True
            }
            persistence.save_boosts([existing_boost])
            
            # Create manager with persistence
            manager = ResourceBoostManager(
                config, metrics, sharing,
                persistence=persistence
            )
            
            # Initialize - should load the boost
            await manager.initialize()
            
            # Check boost was loaded
            assert "existing-boost" in manager._active_boosts
            boost = manager._active_boosts["existing-boost"]
            assert boost.source_node == "gpu1"
            assert boost.amount == 2.0
    
    @pytest.mark.asyncio
    async def test_request_boost_saves_to_persistence(self, mock_dependencies):
        """Test that requesting a boost saves it to persistence."""
        config, metrics, sharing = mock_dependencies
        
        with tempfile.TemporaryDirectory() as tmpdir:
            persistence = ResourceBoostPersistence(data_dir=tmpdir)
            manager = ResourceBoostManager(
                config, metrics, sharing,
                persistence=persistence
            )
            
            await manager.initialize()
            
            # Request a boost
            request = ResourceBoostRequest(
                target_node="gpu-master",
                resource_type=ResourceType.CPU,
                amount=2.0,
                priority=AllocationPriority.NORMAL
            )
            
            boost_id = await manager.request_boost(request)
            
            assert boost_id is not None
            
            # Check it was saved to persistence
            saved_boosts = persistence.load_boosts()
            assert len(saved_boosts) == 1
            assert saved_boosts[0]["boost_id"] == boost_id
            assert saved_boosts[0]["amount"] == 2.0
    
    @pytest.mark.asyncio
    async def test_release_boost_updates_persistence(self, mock_dependencies):
        """Test that releasing a boost updates persistence."""
        config, metrics, sharing = mock_dependencies
        
        with tempfile.TemporaryDirectory() as tmpdir:
            persistence = ResourceBoostPersistence(data_dir=tmpdir)
            manager = ResourceBoostManager(
                config, metrics, sharing,
                persistence=persistence
            )
            
            await manager.initialize()
            
            # Request a boost first
            request = ResourceBoostRequest(
                target_node="gpu-master",
                resource_type=ResourceType.CPU,
                amount=2.0
            )
            
            boost_id = await manager.request_boost(request)
            
            # Verify it's in persistence
            saved_boosts = persistence.load_boosts()
            assert len(saved_boosts) == 1
            
            # Release the boost
            success = await manager.release_boost(boost_id)
            assert success
            
            # Check it was removed from persistence
            saved_boosts = persistence.load_boosts()
            assert len(saved_boosts) == 0
    
    @pytest.mark.asyncio
    async def test_cleanup_expired_boosts(self, mock_dependencies):
        """Test that expired boosts are cleaned up from persistence."""
        config, metrics, sharing = mock_dependencies
        
        with tempfile.TemporaryDirectory() as tmpdir:
            persistence = ResourceBoostPersistence(data_dir=tmpdir)
            
            # Save an expired boost directly to persistence
            expired_boost = {
                "boost_id": "expired-boost",
                "source_node": "gpu1",
                "target_node": "gpu-master",
                "resource_type": ResourceType.CPU,
                "amount": 2.0,
                "allocated_at": datetime.now(UTC) - timedelta(hours=2),
                "expires_at": datetime.now(UTC) - timedelta(hours=1),  # Expired
                "is_active": True
            }
            persistence.save_boosts([expired_boost])
            
            manager = ResourceBoostManager(
                config, metrics, sharing,
                persistence=persistence
            )
            
            await manager.initialize()
            
            # Should not load expired boost
            assert "expired-boost" not in manager._active_boosts
            
            # Run cleanup
            cleaned = await manager.cleanup_expired_boosts()
            
            # Check persistence is clean
            saved_boosts = persistence.load_boosts()
            assert len(saved_boosts) == 0
    
    @pytest.mark.asyncio
    async def test_persistence_error_handling(self, mock_dependencies):
        """Test graceful handling of persistence errors."""
        config, metrics, sharing = mock_dependencies
        
        # Create a persistence that will fail
        persistence = Mock(spec=ResourceBoostPersistence)
        persistence.load_boosts.side_effect = Exception("Load failed")
        persistence.save_boosts.side_effect = Exception("Save failed")
        
        manager = ResourceBoostManager(
            config, metrics, sharing,
            persistence=persistence
        )
        
        # Should not crash even if persistence fails
        await manager.initialize()
        
        # Should still be able to request boosts (even if not saved)
        request = ResourceBoostRequest(
            target_node="gpu-master",
            resource_type=ResourceType.CPU,
            amount=2.0
        )
        
        # This should work even if save fails
        boost_id = await manager.request_boost(request)
        assert boost_id is not None
