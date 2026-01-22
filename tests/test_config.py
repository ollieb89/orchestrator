"""Tests for configuration models."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from distributed_grid.config import ClusterConfig, ExecutionConfig, NodeConfig


def test_node_config_creation(sample_node_config: dict[str, object]) -> None:
    """Test creating a valid node configuration."""
    config = NodeConfig(**sample_node_config)
    assert config.name == "test-node-01"
    assert config.host == "192.168.1.100"
    assert config.gpu_count == 4
    assert config.memory_gb == 64
    assert config.tags == ["gpu", "cuda"]


def test_node_config_ssh_key_path_resolution() -> None:
    """Test SSH key path resolution with tilde expansion."""
    config = NodeConfig(
        name="test",
        host="localhost",
        user="test",
        gpu_count=1,
        memory_gb=16,
        ssh_key_path="~/.ssh/id_rsa",
    )
    assert config.ssh_key_path is not None
    assert str(config.ssh_key_path).endswith(".ssh/id_rsa")


def test_node_config_validation() -> None:
    """Test node configuration validation."""
    with pytest.raises(ValidationError):
        NodeConfig(
            name="test",
            host="localhost",
            user="test",
            gpu_count=-1,  # Invalid negative GPU count
            memory_gb=16,
        )
    
    with pytest.raises(ValidationError):
        NodeConfig(
            name="test",
            host="localhost",
            user="test",
            gpu_count=1,
            memory_gb=0,  # Invalid zero memory
        )


def test_execution_config_defaults() -> None:
    """Test execution configuration default values."""
    config = ExecutionConfig()
    assert config.default_nodes == 1
    assert config.default_gpus_per_node == 1
    assert config.timeout_seconds == 3600
    assert config.retry_attempts == 3
    assert config.working_directory == "/tmp/grid"


def test_execution_config_working_directory_normalization() -> None:
    """Test working directory path normalization."""
    config = ExecutionConfig(working_directory="tmp/grid")
    assert config.working_directory == "/tmp/grid"
    
    config = ExecutionConfig(working_directory="/opt/grid")
    assert config.working_directory == "/opt/grid"


def test_cluster_config_creation(sample_cluster_config_data: dict[str, object]) -> None:
    """Test creating a valid cluster configuration."""
    config = ClusterConfig(**sample_cluster_config_data)
    assert config.name == "test-cluster"
    assert len(config.nodes) == 2
    assert config.execution.default_nodes == 2
    assert config.logging.level == "DEBUG"


def test_cluster_config_validation(invalid_config_data: dict[str, object]) -> None:
    """Test cluster configuration validation."""
    with pytest.raises(ValidationError):
        ClusterConfig(**invalid_config_data)


def test_cluster_config_from_yaml(temp_config_file: Path) -> None:
    """Test loading configuration from YAML file."""
    config = ClusterConfig.from_yaml(temp_config_file)
    assert config.name == "test-cluster"
    assert len(config.nodes) == 2


def test_cluster_config_to_yaml(
    sample_cluster_config: ClusterConfig,
    tmp_path: Path,
) -> None:
    """Test saving configuration to YAML file."""
    output_path = tmp_path / "output_config.yaml"
    sample_cluster_config.to_yaml(output_path)
    
    assert output_path.exists()
    
    # Load it back and verify
    loaded_config = ClusterConfig.from_yaml(output_path)
    assert loaded_config.name == sample_cluster_config.name
    assert len(loaded_config.nodes) == len(sample_cluster_config.nodes)


def test_get_node_by_name(sample_cluster_config: ClusterConfig) -> None:
    """Test getting a node by name."""
    node = sample_cluster_config.get_node_by_name("test-node-01")
    assert node is not None
    assert node.name == "test-node-01"
    assert node.gpu_count == 4
    
    node = sample_cluster_config.get_node_by_name("non-existent")
    assert node is None


def test_get_nodes_by_tag(sample_cluster_config: ClusterConfig) -> None:
    """Test getting nodes by tag."""
    gpu_nodes = sample_cluster_config.get_nodes_by_tag("gpu")
    assert len(gpu_nodes) == 2
    
    tensor_nodes = sample_cluster_config.get_nodes_by_tag("tensor-cores")
    assert len(tensor_nodes) == 1
    assert tensor_nodes[0].name == "test-node-02"
    
    empty_nodes = sample_cluster_config.get_nodes_by_tag("non-existent")
    assert len(empty_nodes) == 0
