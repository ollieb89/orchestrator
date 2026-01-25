import pytest
from unittest.mock import MagicMock
from distributed_grid.orchestration.offloading_executor import ProcessMigrator, ProcessInfo, OffloadingRecommendation
from distributed_grid.config import ClusterConfig
from distributed_grid.orchestration.offloading_executor import OffloadingExecutor

@pytest.mark.asyncio
async def test_migration_script_env_setup_gpu2():
    # Setup
    ssh_manager = MagicMock()
    migrator = ProcessMigrator(ssh_manager)
    
    process = ProcessInfo(
        pid=1234,
        name="node-server",
        cmdline=["node", "server.js"],
        cpu_percent=10.0,
        memory_mb=100.0,
        gpu_memory_mb=0,
        process_type="node"
    )
    
    # Generate script for gpu2
    script = migrator._prepare_migration_script(process, "gpu2")
    
    # Assertions
    # We expect some form of NVM sourcing or valid PATH setup.
    # The current implementation might be missing this depending on internal logic.
    
    # Check that we explicitly try to find npm before exec
    assert 'command -v npm' in script or 'type npm' in script, "Script should verify npm exists"

@pytest.mark.asyncio
async def test_runtime_env_gpu2():
    # Setup
    ssh_manager = MagicMock()
    # Fix ClusterConfig to have at least one node
    from distributed_grid.config import NodeConfig
    node = NodeConfig(name="test-node", host="localhost", user="test", gpu_count=0, memory_gb=16)
    config = ClusterConfig(name="test", nodes=[node])
    executor = OffloadingExecutor(ssh_manager, config)
    
    process = ProcessInfo(
        pid=1234,
        name="node-server",
        cmdline=["node", "server.js"],
        cpu_percent=10.0,
        memory_mb=100.0,
        gpu_memory_mb=0,
        process_type="node"
    )
    
    # Check runtime env for gpu2
    env = executor._prepare_runtime_env("gpu2", process)
    
    # This currently returns {} for gpu2 because of the hardcoded check
    # We expect this assertion to FAIL currently
    assert "env_vars" in env, "Runtime env should contain env_vars for gpu2"
    assert "NVM_DIR" in env["env_vars"], "Runtime env should set NVM_DIR"
