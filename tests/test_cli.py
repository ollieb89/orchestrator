"""Tests for the CLI interface."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from distributed_grid.cli import cli

runner = CliRunner()


def test_cli_init_command(tmp_path: Path) -> None:
    """Test init command creates configuration."""
    config_path = tmp_path / "test_config.yaml"
    
    result = runner.invoke(cli, ["init", "--config", str(config_path)])
    
    assert result.exit_code == 0
    assert config_path.exists()
    
    content = config_path.read_text()
    assert "my-cluster" in content
    assert "node-01" in content


def test_cli_config_validation(tmp_path: Path) -> None:
    """Test config validation command."""
    config_path = tmp_path / "test_config.yaml"
    config_path.write_text("""
name: test-cluster
nodes:
  - name: node-01
    host: 192.168.1.100
    port: 22
    user: testuser
    gpu_count: 4
    memory_gb: 64
execution:
  default_nodes: 1
  default_gpus_per_node: 1
  timeout_seconds: 1800
  retry_attempts: 3
""")
    
    result = runner.invoke(cli, ["config", str(config_path)])
    
    assert result.exit_code == 0
    assert "Configuration is valid" in result.output
