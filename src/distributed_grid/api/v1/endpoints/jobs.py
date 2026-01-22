"""Job management endpoints."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, status

from distributed_grid.schemas.job import Job, JobCreate, JobUpdate, JobStatus
from distributed_grid.services.job_service import JobService

router = APIRouter()
job_service = JobService()


@router.get("/", response_model=List[Job])
async def list_jobs(cluster_id: str = None, node_id: str = None, status: str = None) -> List[Job]:
    """List all jobs, optionally filtered by cluster, node, or status."""
    return await job_service.list_jobs(cluster_id, node_id, status)


@router.post("/", response_model=Job, status_code=status.HTTP_201_CREATED)
async def create_job(job_data: JobCreate) -> Job:
    """Create and submit a new job."""
    try:
        return await job_service.create_job(job_data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{job_id}", response_model=Job)
async def get_job(job_id: str) -> Job:
    """Get a specific job by ID."""
    job = await job_service.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    return job


@router.put("/{job_id}", response_model=Job)
async def update_job(job_id: str, job_data: JobUpdate) -> Job:
    """Update a job."""
    try:
        job = await job_service.update_job(job_id, job_data)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found",
            )
        return job
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete("/{job_id}")
async def delete_job(job_id: str) -> None:
    """Delete a job."""
    success = await job_service.delete_job(job_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )


@router.post("/{job_id}/cancel", response_model=Job)
async def cancel_job(job_id: str) -> Job:
    """Cancel a running job."""
    try:
        job = await job_service.cancel_job(job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found",
            )
        return job
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{job_id}/logs")
async def get_job_logs(job_id: str) -> dict:
    """Get logs for a specific job."""
    try:
        return await job_service.get_job_logs(job_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
