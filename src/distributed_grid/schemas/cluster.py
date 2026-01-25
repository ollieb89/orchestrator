"""Cluster schemas."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, validator


class ClusterBase(BaseModel):
    """Base cluster schema."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    metadata: Optional[dict] = None


class ClusterCreate(ClusterBase):
    """Schema for creating a cluster."""
    pass


class ClusterUpdate(BaseModel):
    """Schema for updating a cluster."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    metadata: Optional[dict] = None


class Cluster(ClusterBase):
    """Schema for a complete cluster."""
    id: str
    created_at: datetime
    updated_at: datetime
    node_count: int = 0
    status: str = "active"

    model_config = ConfigDict(from_attributes=True)


class ClusterSummary(BaseModel):
    """Summary schema for cluster listings."""
    id: str
    name: str
    node_count: int
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
