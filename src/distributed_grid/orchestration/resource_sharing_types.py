"""Data types for resource sharing system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC, timedelta
from enum import Enum
from typing import Dict, Any, Optional

from distributed_grid.monitoring.resource_metrics import ResourceType


class SharingPolicy(str, Enum):
    """Resource sharing policies."""
    CONSERVATIVE = "conservative"  # Only share excess resources
    BALANCED = "balanced"  # Share resources based on pressure
    AGGRESSIVE = "aggressive"  # Proactively share resources
    PREDICTIVE = "predictive"  # Use predictions to anticipate needs


class AllocationPriority(int, Enum):
    """Priority levels for resource allocation."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class ResourceRequest:
    """A request for shared resources."""
    request_id: str
    node_id: str
    resource_type: ResourceType
    amount: float
    priority: AllocationPriority
    duration: Optional[timedelta] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    timeout: Optional[timedelta] = field(default_factory=lambda: timedelta(minutes=5))
    
    @property
    def is_expired(self) -> bool:
        """Check if the request has expired."""
        return datetime.now(UTC) > self.created_at + self.timeout
    
    @property
    def urgency_score(self) -> float:
        """Calculate urgency score based on priority and wait time."""
        wait_time = (datetime.now(UTC) - self.created_at).total_seconds()
        priority_weight = self.priority.value * 0.7
        time_weight = min(wait_time / 300.0, 1.0) * 0.3  # Normalize to 5 minutes
        return priority_weight + time_weight


@dataclass
class ResourceAllocation:
    """An allocation of shared resources."""
    allocation_id: str
    request_id: str
    source_node: str
    target_node: str
    resource_type: ResourceType
    amount: float
    allocated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    lease_duration: Optional[timedelta] = None
    conditions: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_expired(self) -> bool:
        """Check if the allocation has expired."""
        if not self.lease_duration:
            return False
        return datetime.now(UTC) > self.allocated_at + self.lease_duration
