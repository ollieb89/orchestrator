import pytest
from unittest.mock import MagicMock
from distributed_grid.orchestration.offloading_executor import ProcessMigrator
from distributed_grid.orchestration.offloading_detector import ProcessInfo

@pytest.fixture
def mock_ssh_manager():
    return MagicMock()

def test_node_migration_script_for_gpu1(mock_ssh_manager):
    """Test that Node.js processes get NVM setup on gpu1."""
    migrator = ProcessMigrator(mock_ssh_manager)
    
    # Mock Node.js process
    process_info = ProcessInfo(
        pid=12345,
        name="node",
        cmdline=["node", "/tmp/test.js"],
        cpu_percent=10.0,
        memory_mb=100
    )
    
    # Generate script for gpu1
    script = migrator._prepare_migration_script(process_info, "gpu1")
    
    # Verify NVM setup is included
    assert "NVM_DIR" in script
    assert "nvm.sh" in script
    assert "/home/ob/.nvm" in script
    assert "exec node /tmp/test.js" in script or "exec node '/tmp/test.js'" in script


def test_python_migration_script_for_gpu1(mock_ssh_manager):
    """Test that Python processes don't get NVM setup."""
    migrator = ProcessMigrator(mock_ssh_manager)
    
    # Mock Python process
    process_info = ProcessInfo(
        pid=12346,
        name="python",
        cmdline=["python", "script.py"],
        cpu_percent=10.0,
        memory_mb=100
    )
    
    # Generate script for gpu1
    script = migrator._prepare_migration_script(process_info, "gpu1")
    
    # Verify NVM setup is NOT included
    assert "NVM_DIR" not in script
    assert "nvm.sh" not in script
    assert "exec python script.py" in script or "exec python 'script.py'" in script


def test_node_migration_script_for_other_nodes(mock_ssh_manager):
    """Test that Node.js processes on non-gpu1 nodes don't get NVM setup."""
    migrator = ProcessMigrator(mock_ssh_manager)
    
    # Mock Node.js process
    process_info = ProcessInfo(
        pid=12347,
        name="node",
        cmdline=["node", "app.js"],
        cpu_percent=10.0,
        memory_mb=100
    )
    
    # Generate script for gpu2 (not gpu1)
    script = migrator._prepare_migration_script(process_info, "gpu2")
    
    # Verify NVM setup is NOT included (gpu2 might have node in PATH)
    assert "NVM_DIR" not in script
    # Should still execute the command
    assert "exec node app.js" in script or "exec node 'app.js'" in script
