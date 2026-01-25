"""Tests for head-only mode in ResourceMetricsCollector."""

import pytest
from unittest.mock import MagicMock

from distributed_grid.monitoring.resource_metrics import ResourceMetricsCollector
from tests.conftest import get_test_cluster_config


class TestHeadOnlyMode:
    """Test head-only filtering in metrics collector."""

    @pytest.fixture
    def cluster_config(self):
        return get_test_cluster_config()

    @pytest.fixture
    def collector_head_only(self, cluster_config):
        """Collector with head-only mode enabled."""
        collector = ResourceMetricsCollector(
            cluster_config,
            ssh_manager=None,
            collection_interval=1.0,
            head_only_mode=True,
        )
        return collector

    @pytest.fixture
    def collector_all_nodes(self, cluster_config):
        """Collector monitoring all nodes."""
        collector = ResourceMetricsCollector(
            cluster_config,
            ssh_manager=None,
            collection_interval=1.0,
            head_only_mode=False,
        )
        return collector

    def test_head_only_mode_init(self, collector_head_only, cluster_config):
        """Test head-only mode initialization."""
        assert collector_head_only._head_only_mode is True
        assert collector_head_only._head_node_id == cluster_config.nodes[0].name

    def test_all_nodes_mode_init(self, collector_all_nodes):
        """Test all-nodes mode initialization."""
        assert collector_all_nodes._head_only_mode is False

    def test_set_head_only_mode(self, collector_all_nodes):
        """Test runtime toggle of head-only mode."""
        assert collector_all_nodes._head_only_mode is False
        collector_all_nodes.set_head_only_mode(True)
        assert collector_all_nodes._head_only_mode is True

    def test_pressure_callback_head_only(self, collector_head_only):
        """Test that pressure callbacks only fire for head node in head-only mode."""
        triggered_nodes = []

        def callback(node_id, resource_type, pressure):
            triggered_nodes.append(node_id)

        collector_head_only.register_pressure_callback(callback)

        # Simulate high pressure on both head and worker
        collector_head_only._latest_snapshot = {
            "gpu-master": MagicMock(memory_pressure=0.95, cpu_pressure=0.5),
            "gpu1": MagicMock(memory_pressure=0.95, cpu_pressure=0.5),
        }

        # Trigger pressure check
        collector_head_only._check_pressure_events()

        # Only head node should trigger callback
        assert "gpu-master" in triggered_nodes
        assert "gpu1" not in triggered_nodes

    def test_pressure_callback_all_nodes(self, collector_all_nodes):
        """Test that pressure callbacks fire for all nodes when head-only is off."""
        triggered_nodes = []

        def callback(node_id, resource_type, pressure):
            triggered_nodes.append(node_id)

        collector_all_nodes.register_pressure_callback(callback)

        # Simulate high pressure on both nodes
        collector_all_nodes._latest_snapshot = {
            "gpu-master": MagicMock(memory_pressure=0.95, cpu_pressure=0.5),
            "gpu1": MagicMock(memory_pressure=0.95, cpu_pressure=0.5),
        }

        # Trigger pressure check
        collector_all_nodes._check_pressure_events()

        # Both nodes should trigger
        assert "gpu-master" in triggered_nodes
        assert "gpu1" in triggered_nodes
