"""Node schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, validator


class NodeBase(BaseModel):
    """Base node schema."""
    name: str = Field(..., min_length=1, max_length=100)
    host: str = Field(..., min_length=1)
    port: int = Field(default=22, ge=1, le=65535)
    user: str = Field(..., min_length=1)
    gpu_count: int = Field(default=0, ge=0)
    memory_gb: int = Field(default=0, ge=0)
    cpu_cores: int = Field(default=0, ge=0)
    tags: List[str] = Field(default_factory=list)
    metadata: Optional[dict] = None


class NodeCreate(NodeBase):
    """Schema for creating a node."""
    cluster_id: str
    ssh_key_path: Optional[str] = None
    ssh_password: Optional[str] = None


class NodeUpdate(BaseModel):
    """Schema for updating a node."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    host: Optional[str] = Field(None, min_length=1)
    port: Optional[int] = Field(None, ge=1, le=65535)
    user: Optional[str] = Field(None, min_length=1)
    gpu_count: Optional[int] = Field(None, ge=0)
    memory_gb: Optional[int] = Field(None, ge=0)
    cpu_cores: Optional[int] = Field(None, ge=0)
    tags: Optional[List[str]] = None
    metadata: Optional[dict] = None


class Node(NodeBase):
    """Schema for a complete node."""
    id: str
    cluster_id: str
    created_at: datetime
    updated_at: datetime
    status: str = "unknown"
    last_health_check: Optional[datetime] = None
    gpu_utilization: Optional[float] = None
    memory_utilization: Optional[float] = None
    active_jobs: int = 0

    class Config:
        from_attributes = True


class NodeStatus(BaseModel):
    """Schema for node status information."""
    node_id: str
    status: str
    timestamp: datetime
    gpu_utilization: Optional[float] = None
    memory_utilization: Optional[float] = None
    cpu_utilization: Optional[float] = None
    disk_usage: Optional[Dict[str, float]] = None
    temperature: Optional[float] = None
    power_consumption: Optional[float] = None
    error_message: Optional[str] = None


class NodeSummary(BaseModel):
    """Summary schema for node listings."""
    id: str
    name: str
    host: str
    gpu_count: int
    status: str
    active_jobs: int

    class Config:
        from_attributes = True
