"""Tests for offload target validation."""

import pytest
from unittest.mock import MagicMock

from distributed_grid.orchestration.enhanced_offloading_executor import EnhancedOffloadingExecutor
from distributed_grid.orchestration.offloading_detector import OffloadingRecommendation
from tests.conftest import get_test_cluster_config


class TestOffloadTargetValidation:
    """Test that offloading TO head node is rejected."""

    @pytest.fixture
    def cluster_config(self):
        return get_test_cluster_config()

    @pytest.fixture
    def executor(self, cluster_config):
        ssh_manager = MagicMock()
        executor = EnhancedOffloadingExecutor(
            ssh_manager=ssh_manager,
            cluster_config=cluster_config,
            ray_dashboard_address="http://localhost:8265",
        )
        return executor

    def test_reject_offload_to_head_node(self, executor):
        """Test that offloading TO gpu-master is rejected."""
        recommendation = MagicMock(spec=OffloadingRecommendation)
        recommendation.target_node = "gpu-master"
        recommendation.source_node = "gpu1"

        is_valid, reason = executor.validate_offload_target(recommendation)

        assert is_valid is False
        assert "head node" in reason.lower()

    def test_allow_offload_from_head_node(self, executor):
        """Test that offloading FROM gpu-master is allowed."""
        recommendation = MagicMock(spec=OffloadingRecommendation)
        recommendation.target_node = "gpu1"
        recommendation.source_node = "gpu-master"

        is_valid, reason = executor.validate_offload_target(recommendation)

        assert is_valid is True

    def test_allow_offload_between_workers(self, executor):
        """Test that offloading between workers is allowed."""
        recommendation = MagicMock(spec=OffloadingRecommendation)
        recommendation.target_node = "gpu2"
        recommendation.source_node = "gpu1"

        is_valid, reason = executor.validate_offload_target(recommendation)

        assert is_valid is True

    @pytest.mark.asyncio
    async def test_execute_offloading_rejects_invalid_target(self, executor):
        """Test that execute_offloading rejects invalid targets."""
        recommendation = MagicMock(spec=OffloadingRecommendation)
        recommendation.target_node = "gpu-master"
        recommendation.source_node = "gpu1"
        recommendation.process = MagicMock(pid=1234)

        with pytest.raises(ValueError, match="Cannot offload TO head node"):
            await executor.execute_offloading(recommendation)
