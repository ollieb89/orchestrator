"""Tests for AutoOffloadConfig model."""

import pytest
from distributed_grid.config.models import AutoOffloadConfig, ResourceSharingConfig


class TestAutoOffloadConfig:
    """Test AutoOffloadConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = AutoOffloadConfig()
        assert config.enabled is False
        assert config.head_only_mode is True
        assert config.cpu_threshold == 80
        assert config.memory_threshold == 70
        assert config.gpu_threshold == 90
        assert config.check_interval_seconds == 5
        assert config.cooldown_seconds == 30

    def test_custom_thresholds(self):
        """Test custom threshold values."""
        config = AutoOffloadConfig(
            enabled=True,
            cpu_threshold=75,
            memory_threshold=65,
            gpu_threshold=85,
        )
        assert config.enabled is True
        assert config.cpu_threshold == 75
        assert config.memory_threshold == 65
        assert config.gpu_threshold == 85

    def test_threshold_validation(self):
        """Test threshold validation (0-100 range)."""
        with pytest.raises(ValueError):
            AutoOffloadConfig(cpu_threshold=101)
        with pytest.raises(ValueError):
            AutoOffloadConfig(memory_threshold=-1)

    def test_resource_sharing_config_includes_auto_offload(self):
        """Test that ResourceSharingConfig includes auto_offload field."""
        config = ResourceSharingConfig()
        assert hasattr(config, 'auto_offload')
        assert isinstance(config.auto_offload, AutoOffloadConfig)
