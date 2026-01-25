# Offloading Reliability Fix - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix persistent offloading failures on `gpu2` by correcting environment propagation (`npm` path) and generalizing node configuration.

**Architecture:** 
- Update `OffloadingExecutor` to avoid hardcoded node handling.
- Enhance `ProcessMigrator` to generate more robust migration scripts that correctly source `nvm` and verify `npm` availability.
- Add proper environment configuration for `gpu2` (and generic worker nodes).

**Tech Stack:** Python, Ray, Bash, Pytest

---

### Task 1: Reproduce Issue with Unit Test

**Files:**
- Create: `/home/ollie/Development/Tools/cli_tools/orchestrator/tests/distributed_grid/orchestration/test_offloading_env.py`

**Step 1: Write the reproduction test**
Create a test that mocks `ProcessMigrator` and checks the generated script for `gpu2`. It should fail because `gpu2` is not currently handled specially, or the generic fallback is insufficient.

```python
import pytest
from unittest.mock import MagicMock
from distributed_grid.orchestration.offloading_executor import ProcessMigrator, ProcessInfo, OffloadingRecommendation
from distributed_grid.config import ClusterConfig
from distributed_grid.orchestration.offloading_executor import OffloadingExecutor

@pytest.mark.async_api
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

@pytest.mark.async_api
async def test_runtime_env_gpu2():
    # Setup
    ssh_manager = MagicMock()
    config = ClusterConfig(name="test", nodes=[])
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
    assert "env_vars" in env, "Runtime env should contain env_vars for gpu2"
    assert "NVM_DIR" in env["env_vars"], "Runtime env should set NVM_DIR"
```

**Step 2: Run test to verify it fails**
Run: `pixi run pytest tests/distributed_grid/orchestration/test_offloading_env.py -v`
Expected: FAIL - `runtime_env` will be empty for `gpu2`.

**Step 3: Commit**
```bash
git add tests/distributed_grid/orchestration/test_offloading_env.py
git commit -m "test: add reproduction for offloading failure on gpu2"
```

---

### Task 2: Refactor OffloadingExecutor for Generic Node Support

**Files:**
- Modify: `/home/ollie/Development/Tools/cli_tools/orchestrator/src/distributed_grid/orchestration/offloading_executor.py`

**Step 1: Write the fix**
Modify `_prepare_runtime_env` to remove the hardcoded node check.

```python
    def _prepare_runtime_env(
        self, 
        target_node: str, 
        process_info: ProcessInfo
    ) -> Dict[str, Any]:
        """
        Prepare Ray runtime environment based on target node and process type.
        """
        runtime_env = {}
        
        cmdline = process_info.cmdline if isinstance(process_info.cmdline, list) else []
        # Check basic args for 'node'
        is_node_process = any('node' in str(arg).lower() for arg in cmdline[:2])
        
        # Apply Node.js/NVM config for ALL remote nodes if it's a node process
        # Ideally this should be data-driven from NodeConfig, but for now we generalize the 'gpu1' settings
        if is_node_process:
            # Assume 'ob' user for now as persistent user, or try to be more generic.
            # The previous code hardcoded /home/ob. We'll stick to that if it works for gpu2 (likely same user)
            # OR better: use /home/ob which seems to be the standard user for these gpu nodes
            
            runtime_env = {
                "env_vars": {
                    "NVM_DIR": "/home/ob/.nvm",
                    # Add standard paths
                    "PATH": "/home/ob/.nvm/versions/node/v22.21.1/bin:/home/ob/.local/bin:/usr/local/bin:/usr/bin:/bin",
                    "HOME": "/home/ob",
                    "USER": "ob"
                }
            }
            
        return runtime_env
```

**Step 2: Start to run tests**
Run: `pixi run pytest tests/distributed_grid/orchestration/test_offloading_env.py -v`

**Step 3: Commit**
```bash
git add src/distributed_grid/orchestration/offloading_executor.py
git commit -m "fix: generalize runtime_env preparation for all nodes"
```

---

### Task 3: Harden Migration Script

**Files:**
- Modify: `/home/ollie/Development/Tools/cli_tools/orchestrator/src/distributed_grid/orchestration/offloading_executor.py`

**Step 1: Improve `_prepare_migration_script`**
Update the script generation in `ProcessMigrator` to:
1. Try multiple NVM locations (`$HOME/.nvm`, `/usr/local/nvm`, etc).
2. Add diagnostic logging (`echo "PATH is: $PATH"`, `which npm`).
3. Add a check for `npm` and `node` before execution.

```python
# In _prepare_migration_script...
# Add echo statements
script = f"""#!/bin/bash
set -e

echo "Starting migration script..."
echo "Current User: $(whoami)"
echo "Initial PATH: $PATH"

# ... NVM sourcing logic ...

echo "After NVM setup PATH: $PATH"
if ! command -v npm &> /dev/null; then
    echo "ERROR: npm could not be found!"
    exit 127
fi

# ...
"""
```

**Step 2: Run test**
Run: `pixi run pytest tests/distributed_grid/orchestration/test_offloading_env.py -v`

**Step 3: Commit**
```bash
git add src/distributed_grid/orchestration/offloading_executor.py
git commit -m "feat: improve migration script robustness and logging"
```
