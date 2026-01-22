"""Job scheduler for distributing tasks across nodes."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import List, Optional

from distributed_grid.schemas.job import Job
from distributed_grid.schemas.node import Node


class JobScheduler:
    """Schedules jobs across available cluster nodes."""

    def __init__(self) -> None:
        """Initialize the job scheduler."""
        self._pending_jobs: List[Job] = []
        self._running_jobs: dict[str, Job] = {}
        self._completed_jobs: dict[str, Job] = {}

    async def submit_job(self, job: Job) -> None:
        """Submit a job for scheduling."""
        if job.status == "pending":
            self._pending_jobs.append(job)
            await self._schedule_pending_jobs()

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a job."""
        # Remove from pending if not started
        self._pending_jobs = [j for j in self._pending_jobs if j.id != job_id]
        
        # Cancel if running
        if job_id in self._running_jobs:
            job = self._running_jobs[job_id]
            job.status = "cancelled"
            job.updated_at = datetime.utcnow()
            del self._running_jobs[job_id]
            self._completed_jobs[job_id] = job
            # TODO: Actually cancel the running process
            return True
        
        return False

    async def get_job_status(self, job_id: str) -> Optional[Job]:
        """Get the current status of a job."""
        # Check pending jobs
        for job in self._pending_jobs:
            if job.id == job_id:
                return job
        
        # Check running jobs
        if job_id in self._running_jobs:
            return self._running_jobs[job_id]
        
        # Check completed jobs
        if job_id in self._completed_jobs:
            return self._completed_jobs[job_id]
        
        return None

    async def _schedule_pending_jobs(self) -> None:
        """Schedule pending jobs on available nodes."""
        # TODO: Implement actual scheduling logic
        # For now, just mark jobs as running
        while self._pending_jobs:
            job = self._pending_jobs.pop(0)
            job.status = "running"
            job.started_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            self._running_jobs[job.id] = job
            
            # Start job execution in background
            asyncio.create_task(self._execute_job(job))

    async def _execute_job(self, job: Job) -> None:
        """Execute a job."""
        try:
            # TODO: Implement actual job execution
            # Simulate execution with a delay
            await asyncio.sleep(5)
            
            # Mark as completed
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            job.progress = 100.0
            job.result = {"exit_code": 0, "message": "Job completed successfully"}
            
        except Exception as e:
            job.status = "failed"
            job.completed_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            job.error_message = str(e)
        
        finally:
            # Move from running to completed
            if job.id in self._running_jobs:
                del self._running_jobs[job.id]
            self._completed_jobs[job.id] = job
