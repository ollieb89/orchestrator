"""Job schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field, validator


class JobBase(BaseModel):
    """Base job schema."""
    name: str = Field(..., min_length=1, max_length=100)
    command: str = Field(..., min_length=1)
    working_directory: Optional[str] = None
    environment: Dict[str, str] = Field(default_factory=dict)
    requirements: Optional[str] = None
    output_path: Optional[str] = None
    metadata: Optional[dict] = None


class JobCreate(JobBase):
    """Schema for creating a job."""
    cluster_id: str
    node_ids: Optional[List[str]] = None
    gpu_count: int = Field(default=1, ge=0)
    memory_gb: Optional[int] = Field(None, ge=0)
    timeout_seconds: int = Field(default=3600, ge=1)
    retry_attempts: int = Field(default=0, ge=0)
    priority: int = Field(default=0, ge=0, le=100)


class JobUpdate(BaseModel):
    """Schema for updating a job."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    command: Optional[str] = Field(None, min_length=1)
    working_directory: Optional[str] = None
    environment: Optional[Dict[str, str]] = None
    requirements: Optional[str] = None
    output_path: Optional[str] = None
    metadata: Optional[dict] = None
    priority: Optional[int] = Field(None, ge=0, le=100)


class Job(JobBase):
    """Schema for a complete job."""
    id: str
    cluster_id: str
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: str = "pending"
    assigned_nodes: List[str] = Field(default_factory=list)
    gpu_count: int = 1
    memory_gb: Optional[int] = None
    timeout_seconds: int = 3600
    retry_attempts: int = 0
    current_retry: int = 0
    priority: int = 0
    progress: float = 0.0
    result: Optional[dict] = None
    error_message: Optional[str] = None
    logs: Optional[str] = None

    class Config:
        from_attributes = True


class JobStatus(BaseModel):
    """Schema for job status updates."""
    job_id: str
    status: str
    progress: Optional[float] = Field(None, ge=0, le=100)
    timestamp: datetime
    message: Optional[str] = None
    error_message: Optional[str] = None


class JobSummary(BaseModel):
    """Summary schema for job listings."""
    id: str
    name: str
    status: str
    cluster_id: str
    created_at: datetime
    progress: float
    assigned_nodes: List[str]

    class Config:
        from_attributes = True


class JobExecution(BaseModel):
    """Schema for job execution details."""
    job_id: str
    node_id: str
    pid: Optional[int] = None
    exit_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None
