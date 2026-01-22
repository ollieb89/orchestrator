"""Tests for resource sharing functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, UTC, timedelta

from distributed_grid.orchestration.resource_sharing import (
    ResourceSharingManager,
    ResourceSharingProtocol,
    ResourceOffer,
    ResourceRequest,
    ResourceType,
    ResourceAllocation,
)


@pytest.fixture
def mock_ssh_manager():
    """Create a mock SSH manager."""
    manager = AsyncMock()
    manager.get_connected_nodes.return_value = ["node1", "node2"]
    return manager


@pytest.fixture
def resource_sharing_manager(mock_ssh_manager):
    """Create a resource sharing manager for testing."""
    return ResourceSharingManager(
        mock_ssh_manager,
        check_interval=1,
        offer_expiry=60,
    )


class TestResourceSharingProtocol:
    """Test the resource sharing protocol."""

    @pytest.mark.asyncio
    async def test_install_worker_agent(self, mock_ssh_manager):
        """Test installing worker agent on a node."""
        protocol = ResourceSharingProtocol(mock_ssh_manager)
        
        mock_ssh_manager.execute_command.return_value = MagicMock(stdout="Success")
        
        result = await protocol.install_worker_agent("node1")
        
        assert result is True
        mock_ssh_manager.execute_command.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_check_node_resources(self, mock_ssh_manager):
        """Test checking resources on a node."""
        protocol = ResourceSharingProtocol(mock_ssh_manager)
        
        mock_response = {
            "node_id": "node1",
            "offers": [
                {"resource_type": "gpu", "amount": 1},
                {"resource_type": "memory", "amount": 4},
            ]
        }
        mock_ssh_manager.execute_command.return_value = MagicMock(
            stdout=str(mock_response)
        )
        
        result = await protocol.check_node_resources("node1")
        
        assert result == mock_response
    
    @pytest.mark.asyncio
    async def test_execute_remote_job(self, mock_ssh_manager):
        """Test executing a job on a remote node."""
        protocol = ResourceSharingProtocol(mock_ssh_manager)
        
        # Mock successful setup and execution
        mock_ssh_manager.execute_command.side_effect = [
            MagicMock(stdout="Setup complete"),  # Setup
            MagicMock(stdout="Job output"),      # Execution
        ]
        
        success, output = await protocol.execute_remote_job(
            "node1",
            "echo 'Hello World'",
            {"gpu": 1},
        )
        
        assert success is True
        assert output == "Job output"
        assert mock_ssh_manager.execute_command.call_count == 2


class TestResourceSharingManager:
    """Test the resource sharing manager."""
    
    @pytest.mark.asyncio
    async def test_start_stop(self, resource_sharing_manager, mock_ssh_manager):
        """Test starting and stopping the manager."""
        # Mock successful agent installation
        resource_sharing_manager.protocol.install_worker_agent = AsyncMock(
            return_value=True
        )
        
        await resource_sharing_manager.start()
        assert resource_sharing_manager._running is True
        
        await resource_sharing_manager.stop()
        assert resource_sharing_manager._running is False
    
    @pytest.mark.asyncio
    async def test_request_resources(self, resource_sharing_manager):
        """Test requesting resources."""
        # Add a mock offer
        offer = ResourceOffer(
            node_id="node1",
            resource_type=ResourceType.GPU,
            amount=2,
            available_until=datetime.now(UTC) + timedelta(seconds=60),
            conditions={},
        )
        resource_sharing_manager._resource_offers.append(offer)
        
        request = ResourceRequest(
            request_id="test_001",
            resource_type=ResourceType.GPU,
            amount=1,
            priority="medium",
            max_wait_time=300,
        )
        
        allocation = await resource_sharing_manager.request_resources(request)
        
        assert allocation is not None
        assert allocation.request_id == "test_001"
        assert allocation.node_id == "node1"
        assert allocation.amount == 1
    
    @pytest.mark.asyncio
    async def test_request_resources_no_offers(self, resource_sharing_manager):
        """Test requesting resources when no offers are available."""
        request = ResourceRequest(
            request_id="test_002",
            resource_type=ResourceType.GPU,
            amount=1,
            priority="medium",
            max_wait_time=300,
        )
        
        allocation = await resource_sharing_manager.request_resources(request)
        
        assert allocation is None
    
    @pytest.mark.asyncio
    async def test_release_resources(self, resource_sharing_manager):
        """Test releasing allocated resources."""
        # Add an active allocation
        allocation = ResourceAllocation(
            request_id="test_003",
            node_id="node1",
            resource_type=ResourceType.GPU,
            amount=1,
            allocated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(seconds=300),
        )
        resource_sharing_manager._active_allocations["test_003"] = allocation
        
        result = await resource_sharing_manager.release_resources("test_003")
        
        assert result is True
        assert "test_003" not in resource_sharing_manager._active_allocations
    
    @pytest.mark.asyncio
    async def test_execute_on_shared_resources(self, resource_sharing_manager):
        """Test executing a job using shared resources."""
        # Mock the protocol
        resource_sharing_manager.protocol.execute_remote_job = AsyncMock(
            return_value=(True, "Job completed successfully")
        )
        
        # Add a mock offer
        offer = ResourceOffer(
            node_id="node1",
            resource_type=ResourceType.CPU,
            amount=4,
            available_until=datetime.now(UTC) + timedelta(seconds=60),
            conditions={},
        )
        resource_sharing_manager._resource_offers.append(offer)
        
        request = ResourceRequest(
            request_id="test_004",
            resource_type=ResourceType.CPU,
            amount=2,
            priority="medium",
            max_wait_time=300,
        )
        
        success, output = await resource_sharing_manager.execute_on_shared_resources(
            request,
            "echo 'Test job'",
        )
        
        assert success is True
        assert output == "Job completed successfully"
        assert "test_004" not in resource_sharing_manager._active_allocations
    
    def test_get_resource_offers(self, resource_sharing_manager):
        """Test getting current resource offers."""
        offer = ResourceOffer(
            node_id="node1",
            resource_type=ResourceType.MEMORY,
            amount=8,
            available_until=datetime.now(UTC) + timedelta(seconds=60),
            conditions={},
        )
        resource_sharing_manager._resource_offers.append(offer)
        
        offers = resource_sharing_manager.get_resource_offers()
        
        assert len(offers) == 1
        assert offers[0]["node_id"] == "node1"
        assert offers[0]["resource_type"] == "memory"
        assert offers[0]["amount"] == 8
    
    def test_get_active_allocations(self, resource_sharing_manager):
        """Test getting active allocations."""
        allocation = ResourceAllocation(
            request_id="test_005",
            node_id="node2",
            resource_type=ResourceType.GPU,
            amount=1,
            allocated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(seconds=300),
        )
        resource_sharing_manager._active_allocations["test_005"] = allocation
        
        allocations = resource_sharing_manager.get_active_allocations()
        
        assert len(allocations) == 1
        assert allocations[0]["request_id"] == "test_005"
        assert allocations[0]["node_id"] == "node2"
        assert allocations[0]["resource_type"] == "gpu"
    
    @pytest.mark.asyncio
    async def test_cleanup_expired_offers(self, resource_sharing_manager):
        """Test cleanup of expired offers."""
        # Add an expired offer
        expired_offer = ResourceOffer(
            node_id="node1",
            resource_type=ResourceType.GPU,
            amount=1,
            available_until=datetime.now(UTC) - timedelta(seconds=10),  # Expired
            conditions={},
        )
        # Add a valid offer
        valid_offer = ResourceOffer(
            node_id="node2",
            resource_type=ResourceType.GPU,
            amount=1,
            available_until=datetime.now(UTC) + timedelta(seconds=60),  # Valid
            conditions={},
        )
        
        resource_sharing_manager._resource_offers = [expired_offer, valid_offer]
        
        await resource_sharing_manager._cleanup_expired_offers()
        
        assert len(resource_sharing_manager._resource_offers) == 1
        assert resource_sharing_manager._resource_offers[0].node_id == "node2"
