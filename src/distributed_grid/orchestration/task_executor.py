"""Task executor for running jobs on nodes."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Dict, List, Optional

from distributed_grid.core.ssh_manager import SSHManager
from distributed_grid.schemas.job import Job
from distributed_grid.schemas.node import Node


class TaskExecutor:
    """Executes tasks on remote nodes via SSH."""

    def __init__(self) -> None:
        """Initialize the task executor."""
        self._ssh_manager = SSHManager()
        self._running_tasks: dict[str, asyncio.Task] = {}

    async def execute_job(self, job: Job, node: Node) -> Dict[str, object]:
        """Execute a job on a specific node."""
        # Prepare execution environment
        work_dir = job.working_directory or "/tmp/grid"
        
        # Create remote working directory
        await self._ssh_manager.execute_command(
            node,
            f"mkdir -p {work_dir}",
        )
        
        # Upload requirements if provided
        if job.requirements:
            requirements_file = Path(work_dir) / "requirements.txt"
            await self._ssh_manager.write_file(
                node,
                str(requirements_file),
                job.requirements,
            )
            
            # Install requirements
            install_cmd = f"cd {work_dir} && pip install -r requirements.txt"
            await self._ssh_manager.execute_command(node, install_cmd)
        
        # Prepare environment variables
        env_vars = " ".join(
            f"export {k}='{v}' && "
            for k, v in job.environment.items()
        )
        
        # Execute the command
        full_command = f"{env_vars} cd {work_dir} && {job.command}"
        
        # Capture output
        stdout, stderr, exit_code = await self._ssh_manager.execute_command(
            node,
            full_command,
            timeout=job.timeout_seconds,
        )
        
        # Prepare result
        result = {
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "node_id": node.id,
            "command": job.command,
        }
        
        # Download output files if specified
        if job.output_path:
            # TODO: Implement file download
            pass
        
        return result

    async def execute_job_parallel(
        self,
        job: Job,
        nodes: List[Node],
    ) -> List[Dict[str, object]]:
        """Execute a job in parallel across multiple nodes."""
        tasks = []
        
        for node in nodes:
            task = asyncio.create_task(self.execute_job(job, node))
            tasks.append(task)
            self._running_tasks[f"{job.id}_{node.id}"] = task
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Clean up task tracking
        for node in nodes:
            task_key = f"{job.id}_{node.id}"
            self._running_tasks.pop(task_key, None)
        
        return results

    async def cancel_execution(self, job_id: str, node_id: str) -> bool:
        """Cancel a running job execution."""
        task_key = f"{job_id}_{node_id}"
        
        if task_key in self._running_tasks:
            task = self._running_tasks[task_key]
            task.cancel()
            
            try:
                await task
            except asyncio.CancelledError:
                pass
            
            # Kill remote processes
            # TODO: Implement proper process tracking and killing
            return True
        
        return False

    async def stream_output(
        self,
        job: Job,
        node: Node,
    ) -> None:
        """Stream job output in real-time."""
        # TODO: Implement real-time output streaming
        pass
