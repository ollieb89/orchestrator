"""Test CLI memory commands."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from distributed_grid.cli import cli
from tests.conftest import get_test_cluster_config


@pytest.mark.asyncio
async def test_memory_store_command() -> None:
    """Test storing data via CLI."""
    runner = CliRunner()
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("test data")
        temp_path = f.name
    
    try:
        result = runner.invoke(cli, [
            "memory", "store", "test-key", temp_path,
            "--config", str(Path(__file__).parent.parent / "config" / "my-cluster-enhanced.yaml")
        ])
        assert result.exit_code == 0
        assert "Stored data" in result.output
        
    finally:
        Path(temp_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_memory_retrieve_command() -> None:
    """Test retrieving data via CLI."""
    runner = CliRunner()
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("retrieve test data")
        temp_path = f.name
    
    try:
        # Store some data first
        result = runner.invoke(cli, [
            "memory", "store", "retrieve-test", temp_path,
            "--config", str(Path(__file__).parent.parent / "config" / "my-cluster-enhanced.yaml")
        ])
        assert result.exit_code == 0
        
        # Retrieve the data
        result = runner.invoke(cli, [
            "memory", "retrieve", "retrieve-test",
            "--config", str(Path(__file__).parent.parent / "config" / "my-cluster-enhanced.yaml")
        ])
        
        assert result.exit_code == 0
        assert "retrieve test data" in result.output
        
    finally:
        Path(temp_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_memory_list_objects_command() -> None:
    """Test listing objects via CLI."""
    runner = CliRunner()
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("list test data")
        temp_path = f.name
    
    try:
        # Store some data first
        result = runner.invoke(cli, [
            "memory", "store", "list-test-key", temp_path,
            "--config", str(Path(__file__).parent.parent / "config" / "my-cluster-enhanced.yaml")
        ])
        assert result.exit_code == 0
        
        # List objects
        result = runner.invoke(cli, [
            "memory", "list-objects",
            "--config", str(Path(__file__).parent.parent / "config" / "my-cluster-enhanced.yaml")
        ])
        
        assert result.exit_code == 0
        assert "Distributed Memory Objects" in result.output
        assert "list-test-key" in result.output
        
    finally:
        Path(temp_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_memory_retrieve_nonexistent_key() -> None:
    """Test retrieving non-existent key."""
    runner = CliRunner()
    
    result = runner.invoke(cli, [
        "memory", "retrieve", "nonexistent-key",
        "--config", str(Path(__file__).parent.parent / "config" / "my-cluster-enhanced.yaml")
    ])
    
    assert result.exit_code == 0
    assert "not found" in result.output


@pytest.mark.asyncio
async def test_memory_store_with_node_hint() -> None:
    """Test storing data with node hint."""
    runner = CliRunner()
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("node hint test")
        temp_path = f.name
    
    try:
        result = runner.invoke(cli, [
            "memory", "store", "node-hint-test", temp_path,
            "--node", "gpu-master",
            "--config", str(Path(__file__).parent.parent / "config" / "my-cluster-enhanced.yaml")
        ])
        assert result.exit_code == 0
        
    finally:
        Path(temp_path).unlink(missing_ok=True)
