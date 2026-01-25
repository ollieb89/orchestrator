"""Process offloading executor using Ray jobs."""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

import structlog
import yaml
from ray.dashboard.modules.job.sdk import JobSubmissionClient
from ray.dashboard.modules.job.common import JobStatus

from distributed_grid.core.ssh_manager import SSHManager
from distributed_grid.config import ClusterConfig, NodeConfig
from distributed_grid.orchestration.offloading_detector import (
    ProcessInfo,
    OffloadingRecommendation,
    ProcessType,
)

logger = structlog.get_logger(__name__)


class OffloadingStatus(str, Enum):
    """Status of an offloading operation."""
    PENDING = "pending"
    PREPARING = "preparing"
    SUBMITTING = "submitting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class OffloadingTask:
    """A task for offloading a process."""
    task_id: str
    recommendation: OffloadingRecommendation
    status: OffloadingStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    ray_job_id: Optional[str] = None
    error_message: Optional[str] = None
    progress: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.progress is None:
            self.progress = {}


class ProcessMigrator:
    """Handles the migration of processes between nodes."""
    
    def __init__(self, ssh_manager: SSHManager):
        """Initialize the process migrator."""
        self.ssh_manager = ssh_manager
    
    async def capture_process_state(self, node_id: str, process: ProcessInfo) -> Dict:
        """Capture the state of a process for migration."""
        logger.info("Capturing process state", node=node_id, pid=process.pid)
        
        # Get process environment
        env_cmd = f"cat /proc/{process.pid}/environ 2>/dev/null | tr '\\0' '\\n'"
        env_result = await self.ssh_manager.run_command(node_id, env_cmd, timeout=5)
        
        environment = {}
        if env_result.exit_status == 0:
            for line in env_result.stdout.split("\n"):
                if "=" in line:
                    key, value = line.split("=", 1)
                    environment[key] = value
        
        # Get working directory
        cwd_cmd = f"readlink /proc/{process.pid}/cwd 2>/dev/null"
        cwd_result = await self.ssh_manager.run_command(node_id, cwd_cmd, timeout=5)
        
        working_dir = cwd_result.stdout.strip() if cwd_result.exit_status == 0 else None
        
        # Get open files (for checkpointing)
        files_cmd = f"lsof -p {process.pid} 2>/dev/null | grep -E '\\.(log|ckpt|model|pkl|h5)'"
        files_result = await self.ssh_manager.run_command(node_id, files_cmd, timeout=5)
        
        open_files = []
        if files_result.exit_status == 0:
            for line in files_result.stdout.split("\n"):
                parts = line.split()
                if len(parts) >= 9:
                    open_files.append(parts[8])
        
        return {
            "environment": environment,
            "working_dir": working_dir,
            "open_files": open_files,
            "command": " ".join(process.cmdline),
        }
    
    def _prepare_migration_script(self, process_info: ProcessInfo, target_node: str) -> str:
        """
        Prepare migration script with specialized handling for Node.js processes.
        
        Args:
            process_info: Information about the process to migrate
            target_node: Target node identifier (e.g., 'gpu1', '192.168.1.101')
            
        Returns:
            Bash script content as string
        """
        # Extract command line from ProcessInfo
        cmdline = process_info.cmdline if isinstance(process_info.cmdline, list) else []
        
        if not cmdline:
            # Fallback if empty
            cmdline = [process_info.name]
        
        # Detect if this is a Node.js process
        is_node_process = (
            'node' in cmdline[0].lower() or 
            any('node' in str(arg).lower() for arg in cmdline[:2])
        )
        
        # Check if target is gpu1 (needs NVM setup)
        needs_nvm = target_node in ['gpu1', '192.168.1.101']
        
        # Build the command string with proper escaping
        import shlex
        # Filter empty args and convert to string
        clean_cmdline = [str(arg) for arg in cmdline if arg]
        escaped_cmdline = ' '.join(shlex.quote(arg) for arg in clean_cmdline)
        
        # Generate script based on process type and target
        if is_node_process and needs_nvm:
            script = f"""#!/bin/bash
set -e

# Setup NVM environment for Node.js processes on gpu1
export NVM_DIR="/home/ob/.nvm"
if [ -s "$NVM_DIR/nvm.sh" ]; then
    source "$NVM_DIR/nvm.sh"
fi

# Ensure Node.js is in PATH
export PATH="/home/ob/.nvm/versions/node/v22.21.1/bin:$PATH"
export HOME="/home/ob"
export USER="ob"

# Execute the migrated process
exec {escaped_cmdline}
"""
        else:
            # Standard migration script
            script = f"""#!/bin/bash
set -e

# Execute the migrated process
exec {escaped_cmdline}
"""
        
        return script

    async def create_migration_script(
        self,
        process: ProcessInfo,
        state: Dict,
        target_env: Dict[str, str],
        target_node: str,
    ) -> str:
        """Create a script to restart the process on the target node."""
        
        # Get base script with NVM setup if needed
        base_script = self._prepare_migration_script(process, target_node)
        
        # Generate environment exports
        env_exports_list = []
        
        # Add migration metadata
        env_exports_list.append(f'export MIGRATED_FROM_PID={process.pid}')
        env_exports_list.append(f'export MIGRATION_TIME={datetime.now(UTC).isoformat()}')
        
        # Add environment variables
        import shlex
        for key, value in target_env.items():
            env_exports_list.append(f'export {key}={shlex.quote(str(value))}')
        
        # Add original environment (filtered)
        if state.get("environment"):
            for key, value in state["environment"].items():
                if not key.startswith(("SSH_", "DISPLAY", "XDG_")):
                    env_exports_list.append(f'export {key}={shlex.quote(str(value))}')
        
        env_exports = '\n'.join(env_exports_list)
        
        # Handle working directory
        cwd_cmd = ""
        if state.get("working_dir"):
            cwd_cmd = f'\n# Change to working directory\ncd "{state["working_dir"]}"\n'
            
        # Insert environment exports before the exec command
        script_lines = base_script.split('\n')
        
        try:
            # Find where to insert (before exec)
            exec_line_idx = next(
                i for i, line in enumerate(script_lines) 
                if line.strip().startswith('exec ')
            )
            
            # Insert logic
            script_lines.insert(exec_line_idx, cwd_cmd)
            script_lines.insert(exec_line_idx, '\n# Restore process environment\n' + env_exports + '\n')
            
            return '\n'.join(script_lines)
            
        except StopIteration:
            # Fallback if no exec line found (should not happen with _prepare_migration_script)
            return base_script


class OffloadingExecutor:
    """Executes process offloading using Ray jobs."""
    
    def __init__(
        self,
        ssh_manager: SSHManager,
        cluster_config: ClusterConfig,
        ray_dashboard_address: str = "http://localhost:8265",
    ):
        """Initialize the offloading executor."""
        self.ssh_manager = ssh_manager
        self.cluster_config = cluster_config
        self.ray_dashboard_address = ray_dashboard_address
        self.migrator = ProcessMigrator(ssh_manager)
        
        # Active offloading tasks
        self._active_tasks: Dict[str, OffloadingTask] = {}
        self._task_history: List[OffloadingTask] = []
        
        # Ray job client
        self._job_client: Optional[JobSubmissionClient] = None
    
    async def initialize(self) -> None:
        """Initialize the executor."""
        # Initialize Ray job client
        self._job_client = JobSubmissionClient(self.ray_dashboard_address)
        logger.info("Offloading executor initialized", dashboard=self.ray_dashboard_address)
    
    async def execute_offloading(
        self,
        recommendation: OffloadingRecommendation,
        capture_state: bool = True,
        runtime_env: Optional[Dict] = None,
    ) -> str:
        """Execute an offloading operation."""
        task_id = f"offload_{int(time.time())}_{recommendation.process.pid}"
        
        task = OffloadingTask(
            task_id=task_id,
            recommendation=recommendation,
            status=OffloadingStatus.PENDING,
            created_at=datetime.now(UTC),
        )
        
        self._active_tasks[task_id] = task
        logger.info("Starting offloading", task_id=task_id, pid=recommendation.process.pid)
        
        try:
            # Step 1: Prepare
            task.status = OffloadingStatus.PREPARING
            await self._prepare_offloading(task, capture_state)
            
            # Step 2: Submit to Ray
            task.status = OffloadingStatus.SUBMITTING
            
            # Prepare specialized runtime env if not provided
            if runtime_env is None:
                runtime_env_config = self._prepare_runtime_env(
                    task.recommendation.target_node,
                    recommendation.process
                )
                # Combine with basic env if needed, or pass as is
                # For now, we will merge it into the submit call
            else:
                runtime_env_config = runtime_env

            ray_job_id = await self._submit_ray_job(task, runtime_env_config)
            task.ray_job_id = ray_job_id
            
            # Step 3: Monitor
            task.status = OffloadingStatus.RUNNING
            task.started_at = datetime.now(UTC)
            
            # Start monitoring task
            asyncio.create_task(self._monitor_job(task))
            
            return task_id
            
        except Exception as e:
            task.status = OffloadingStatus.FAILED
            task.error_message = str(e)
            task.completed_at = datetime.now(UTC)
            logger.error("Offloading failed", task_id=task_id, error=str(e))
            raise
    
    async def _prepare_offloading(self, task: OffloadingTask, capture_state: bool) -> None:
        """Prepare for offloading by capturing process state."""
        process = task.recommendation.process
        
        if capture_state:
            # Capture process state from source node
            state = await self.migrator.capture_process_state(
                "gpu-master",  # TODO: Get actual source node
                process,
            )
            task.progress["captured_state"] = state
        
        # Create migration script
        state = task.progress.get("captured_state", {
            "environment": {},
            "working_dir": None,
            "open_files": [],
            "command": " ".join(process.cmdline),
        })
        
        # Prepare target environment
        target_env = await self._prepare_target_environment(task)
        
        migration_script = await self.migrator.create_migration_script(
            process,
            state,
            target_env,
            task.recommendation.target_node,
        )
        
        task.progress["migration_script"] = migration_script
        task.progress["target_env"] = target_env
    
    async def _prepare_target_environment(self, task: OffloadingTask) -> Dict[str, str]:
        """Prepare the target environment for the process."""
        target_node = task.recommendation.target_node
        
        # Basic environment setup
        env = {
            "TARGET_NODE": target_node,
            "OFFLOADING_TASK_ID": task.task_id,
        }
        
        # Add GPU-specific environment
        if task.recommendation.process.gpu_memory_mb > 0:
            env["CUDA_VISIBLE_DEVICES"] = "0"
            env["GPU_MEMORY_GB"] = str(task.recommendation.process.gpu_memory_mb // 1024)
        
        # Add resource constraints
        for resource, (required, available) in task.recommendation.resource_match.items():
            env[f"LIMIT_{resource.upper()}"] = str(required)
        
        return env
    
    async def _submit_ray_job(self, task: OffloadingTask, runtime_env: Optional[Dict]) -> str:
        """Submit the offloading as a Ray job."""
        
        # Create a temporary directory for the job
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Write the migration script
            script_path = temp_path / "migration_script.sh"
            with open(script_path, "w") as f:
                f.write(task.progress["migration_script"])
            
            # Create a Python wrapper script
            wrapper_script = self._create_ray_job_wrapper(task)
            wrapper_path = temp_path / "job.py"
            with open(wrapper_path, "w") as f:
                f.write(wrapper_script)
            
            # Prepare runtime environment
            if runtime_env is None:
                runtime_env = {
                    "working_dir": str(temp_path),
                    "env_vars": task.progress["target_env"],
                }
            
            # Submit the job
            job_id = self._job_client.submit_job(
                entrypoint=f"python job.py",
                runtime_env=runtime_env,
                metadata={
                    "task_id": task.task_id,
                    "source_pid": str(task.recommendation.process.pid),
                    "target_node": task.recommendation.target_node,
                },
            )
            
            logger.info("Ray job submitted", task_id=task.task_id, job_id=job_id)
            return job_id
    
    def _prepare_runtime_env(
        self, 
        target_node: str, 
        process_info: ProcessInfo
    ) -> Dict[str, Any]:
        """
        Prepare Ray runtime environment based on target node and process type.
        
        Args:
            target_node: Target node identifier
            process_info: Process information
            
        Returns:
            Runtime environment dictionary for Ray
        """
        runtime_env = {}
        
        # For gpu1, ensure Node.js and NVM are available
        if target_node in ['gpu1', '192.168.1.101']:
            cmdline = process_info.cmdline if isinstance(process_info.cmdline, list) else []
            # Check basic args for 'node'
            is_node_process = any('node' in str(arg).lower() for arg in cmdline[:2])
            
            if is_node_process:
                runtime_env = {
                    "env_vars": {
                        "NVM_DIR": "/home/ob/.nvm",
                        "PATH": "/home/ob/.nvm/versions/node/v22.21.1/bin:/home/ob/.local/bin:/usr/local/bin:/usr/bin:/bin",
                        "HOME": "/home/ob",
                        "USER": "ob"
                    }
                }
        
        return runtime_env
    
    def _create_ray_job_wrapper(self, task: OffloadingTask) -> str:
        """Create a Python wrapper script for the Ray job."""
        
        return f'''"""
Ray job wrapper for offloading task {task.task_id}
"""

import subprocess
import sys
import os
import time
import json
from pathlib import Path

def main():
    """Execute the offloaded process."""
    print(f"Starting offloaded process for task {task.task_id}")
    
    # Update progress
    progress_file = Path("progress.json")
    progress = {{
        "status": "running",
        "started_at": time.time(),
        "node": os.environ.get("RAY_NODE_ID", "unknown"),
    }}
    
    with open(progress_file, "w") as f:
        json.dump(progress, f)
    
    # Execute the migration script
    script_path = "migration_script.sh"
    if not os.path.exists(script_path):
        print(f"Error: Migration script not found at {{script_path}}")
        sys.exit(1)
    
    # Make script executable
    os.chmod(script_path, 0o755)
    
    # Run the script
    try:
        result = subprocess.run(
            ["bash", script_path],
            capture_output=True,
            text=True,
        )
        
        if result.returncode != 0:
            print(f"Process failed with exit code {{result.returncode}}")
            print(f"STDERR: {{result.stderr}}")
            sys.exit(result.returncode)
        
        print("Process completed successfully")
        print(f"Output: {{result.stdout}}")
        
        # Update progress
        progress["status"] = "completed"
        progress["completed_at"] = time.time()
        with open(progress_file, "w") as f:
            json.dump(progress, f)
            
    except Exception as e:
        print(f"Error executing process: {{e}}")
        progress["status"] = "failed"
        progress["error"] = str(e)
        progress["failed_at"] = time.time()
        with open(progress_file, "w") as f:
            json.dump(progress, f)
        sys.exit(1)

if __name__ == "__main__":
    main()
'''
    
    async def _monitor_job(self, task: OffloadingTask) -> None:
        """Monitor a running Ray job."""
        if not self._job_client:
            return
        
        try:
            while task.status == OffloadingStatus.RUNNING:
                # Get job status
                job_status = self._job_client.get_job_status(task.ray_job_id)
                
                if job_status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.STOPPED}:
                    task.status = OffloadingStatus.COMPLETED if job_status == JobStatus.SUCCEEDED else OffloadingStatus.FAILED
                    task.completed_at = datetime.now(UTC)
                    
                    # Move to history
                    self._task_history.append(task)
                    del self._active_tasks[task.task_id]
                    
                    logger.info(
                        "Offloading completed",
                        task_id=task.task_id,
                        status=task.status,
                    )
                    break
                
                await asyncio.sleep(5)
                
        except Exception as e:
            logger.error("Job monitoring failed", task_id=task.task_id, error=str(e))
            task.status = OffloadingStatus.FAILED
            task.error_message = str(e)
            task.completed_at = datetime.now(UTC)
    
    async def cancel_offloading(self, task_id: str) -> bool:
        """Cancel an active offloading task."""
        if task_id not in self._active_tasks:
            return False
        
        task = self._active_tasks[task_id]
        
        try:
            if task.ray_job_id and self._job_client:
                self._job_client.stop_job(task.ray_job_id)
            
            task.status = OffloadingStatus.CANCELLED
            task.completed_at = datetime.now(UTC)
            
            # Move to history
            self._task_history.append(task)
            del self._active_tasks[task_id]
            
            logger.info("Offloading cancelled", task_id=task_id)
            return True
            
        except Exception as e:
            logger.error("Failed to cancel offloading", task_id=task_id, error=str(e))
            return False
    
    def get_task_status(self, task_id: str) -> Optional[OffloadingTask]:
        """Get the status of an offloading task."""
        return self._active_tasks.get(task_id)
    
    def list_active_tasks(self) -> List[OffloadingTask]:
        """List all active offloading tasks."""
        return list(self._active_tasks.values())
    
    def get_task_history(self, limit: int = 100) -> List[OffloadingTask]:
        """Get the history of offloading tasks."""
        return self._task_history[-limit:]
    
    async def get_offloading_statistics(self) -> Dict:
        """Get statistics about offloading operations."""
        stats = {
            "total_tasks": len(self._task_history) + len(self._active_tasks),
            "active_tasks": len(self._active_tasks),
            "completed_tasks": 0,
            "failed_tasks": 0,
            "cancelled_tasks": 0,
            "by_target_node": {},
            "by_process_type": {},
            "average_duration": 0,
        }
        
        durations = []
        
        # Process in-memory tasks
        for task in self._task_history:
            if task.status == OffloadingStatus.COMPLETED:
                stats["completed_tasks"] += 1
            elif task.status == OffloadingStatus.FAILED:
                stats["failed_tasks"] += 1
            elif task.status == OffloadingStatus.CANCELLED:
                stats["cancelled_tasks"] += 1
            
            # Statistics
            target = task.recommendation.target_node
            stats["by_target_node"][target] = stats["by_target_node"].get(target, 0) + 1
            
            proc_type = task.recommendation.process.process_type or "unknown"
            stats["by_process_type"][proc_type] = stats["by_process_type"].get(proc_type, 0) + 1
            
            # Duration
            if task.started_at and task.completed_at:
                duration = (task.completed_at - task.started_at).total_seconds()
                durations.append(duration)
        
        # Query Ray job API for historical jobs
        if self._job_client:
            try:
                # Get all jobs from Ray
                jobs = self._job_client.list_jobs()
                
                # Filter jobs that have our metadata (indicating they are offloading tasks)
                offloading_jobs = [
                    job for job in jobs 
                    if job.metadata and "task_id" in job.metadata
                ]
                
                # Add historical jobs not already in memory
                existing_task_ids = {task.task_id for task in self._task_history}
                
                for job in offloading_jobs:
                    if job.job_id not in existing_task_ids:
                        # Count by status
                        if job.status == JobStatus.SUCCEEDED:
                            stats["completed_tasks"] += 1
                        elif job.status == JobStatus.FAILED:
                            stats["failed_tasks"] += 1
                        elif job.status == JobStatus.STOPPED:
                            stats["cancelled_tasks"] += 1
                        
                        # Extract target node from metadata
                        target_node = job.metadata.get("target_node", "unknown")
                        stats["by_target_node"][target_node] = stats["by_target_node"].get(target_node, 0) + 1
                        
                        # Update total count
                        stats["total_tasks"] += 1
                        
            except Exception as e:
                logger.warning("Failed to query Ray job history", error=str(e))
        
        if durations:
            stats["average_duration"] = sum(durations) / len(durations)
        
        return stats
