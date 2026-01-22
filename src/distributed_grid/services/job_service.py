"""Job service for managing job operations."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from distributed_grid.schemas.job import Job, JobCreate, JobStatus, JobUpdate


class JobService:
    """Service for managing jobs."""

    def __init__(self) -> None:
        """Initialize the job service."""
        # TODO: Replace with actual database/storage
        self._jobs: dict[str, Job] = {}

    async def list_jobs(
        self,
        cluster_id: Optional[str] = None,
        node_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Job]:
        """List all jobs, optionally filtered."""
        jobs = list(self._jobs.values())
        
        if cluster_id:
            jobs = [j for j in jobs if j.cluster_id == cluster_id]
        
        if node_id:
            jobs = [j for j in jobs if node_id in j.assigned_nodes]
        
        if status:
            jobs = [j for j in jobs if j.status == status]
        
        return jobs

    async def get_job(self, job_id: str) -> Optional[Job]:
        """Get a job by ID."""
        return self._jobs.get(job_id)

    async def create_job(self, job_data: JobCreate) -> Job:
        """Create and submit a new job."""
        job_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        job = Job(
            id=job_id,
            created_at=now,
            updated_at=now,
            cluster_id=job_data.cluster_id,
            assigned_nodes=job_data.node_ids or [],
            **job_data.dict(exclude={"cluster_id", "node_ids"}),
        )
        
        self._jobs[job_id] = job
        
        # TODO: Actually submit the job to the cluster
        # For now, just mark it as pending
        
        return job

    async def update_job(
        self,
        job_id: str,
        job_data: JobUpdate,
    ) -> Optional[Job]:
        """Update a job."""
        job = self._jobs.get(job_id)
        if not job:
            return None
        
        update_data = job_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(job, field, value)
        
        job.updated_at = datetime.utcnow()
        return job

    async def delete_job(self, job_id: str) -> bool:
        """Delete a job."""
        if job_id in self._jobs:
            del self._jobs[job_id]
            return True
        return False

    async def cancel_job(self, job_id: str) -> Optional[Job]:
        """Cancel a running job."""
        job = self._jobs.get(job_id)
        if not job:
            return None
        
        if job.status in ["running", "pending"]:
            job.status = "cancelled"
            job.updated_at = datetime.utcnow()
            # TODO: Actually cancel the job execution
            
        return job

    async def get_job_logs(self, job_id: str) -> Dict[str, str]:
        """Get logs for a specific job."""
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        
        # TODO: Implement actual log retrieval
        return {
            "stdout": job.logs or "",
            "stderr": "",
            "combined": job.logs or "",
        }
