
import asyncio
import pytest
from unittest.mock import MagicMock, patch, ANY
from distributed_grid.orchestration.offloading_executor import OffloadingExecutor, OffloadingRecommendation
from distributed_grid.orchestration.offloading_detector import ProcessInfo

@pytest.mark.asyncio
async def test_offloading_runtime_env_bug():
    """
    Reproduction test for bug where runtime_env passed to execute_offloading
    overwrites the working_dir setting needed for the job wrapper.
    """
    # Mock dependencies
    ssh_manager = MagicMock()
    cluster_config = MagicMock()
    
    # Create executor
    executor = OffloadingExecutor(ssh_manager, cluster_config)
    executor._job_client = MagicMock()
    executor._job_client.submit_job.return_value = "job_123"
    
    # Mock helper methods to avoid side effects
    executor._prepare_offloading = MagicMock()
    executor.migrator.capture_process_state = MagicMock(return_value={})
    
    # Create a recommendation
    process = ProcessInfo(pid=123, name="test", cmdline=["python", "test.py"], memory_mb=100, cpu_percent=1.0)
    recommendation = OffloadingRecommendation(
        process=process, 
        source_node="master",
        target_node="gpu2", 
        confidence=0.9, 
        reason="test",
        resource_match={},
        migration_complexity="low"
    )
    
    # Mock internal state needed for _submit_ray_job
    task_id = f"offload_123_{process.pid}"
    # We need to bypass the real _submit_ray_job calling logic which depends on task state
    # So we'll test _submit_ray_job directly or verify the call arguments of submit_job
    
    # But wait, we want to test correct integration in execute_offloading or _submit_ray_job
    # Let's mock _prepare_offloading to set up the task state correctly
    async def mock_prepare(task, capture_state):
        task.progress["migration_script"] = "#!/bin/bash\necho test"
        task.progress["target_env"] = {"TEST_VAR": "val"}
    
    executor._prepare_offloading = mock_prepare
    async def mock_monitor(task):
        pass
    executor._monitor_job = mock_monitor # Don't start monitoring loop
    
    # EXECUTE with a custom runtime_env (this triggered the bug)
    # The bug was: if runtime_env is passed, working_dir in _submit_ray_job is skipped
    custom_runtime_env = {"env_vars": {"CUSTOM": "1"}}
    
    try:
        await executor.execute_offloading(recommendation, capture_state=False, runtime_env=custom_runtime_env)
    except Exception as e:
        pytest.fail(f"Execution failed: {e}")
        
    # Verify what submit_job was called with
    call_args = executor._job_client.submit_job.call_args
    assert call_args is not None
    
    _, kwargs = call_args
    submitted_runtime_env = kwargs.get("runtime_env")
    
    print(f"Submitted runtime_env: {submitted_runtime_env}")
    
    # assertion failure expected here before fix
    assert "working_dir" in submitted_runtime_env, "working_dir missing from runtime_env!"
    assert submitted_runtime_env["working_dir"], "working_dir should not be empty"
    
    # Also verify our custom env is preserved
    if "env_vars" in submitted_runtime_env:
        assert submitted_runtime_env["env_vars"].get("CUSTOM") == "1", "Custom env vars lost!"

