"""Configuration models for Distributed Grid."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator


class NodeConfig(BaseModel):
    """Configuration for a single node in the cluster."""
    
    name: str = Field(..., description="Unique name for the node")
    host: str = Field(..., description="Hostname or IP address")
    port: int = Field(22, description="SSH port")
    user: str = Field(..., description="SSH username")
    gpu_count: int = Field(..., ge=0, description="Number of GPUs available")
    memory_gb: int = Field(..., ge=1, description="Memory in GB")
    ssh_key_path: Optional[Path] = Field(None, description="Path to SSH private key")
    tags: List[str] = Field(default_factory=list, description="Node tags")
    
    @field_validator("ssh_key_path", mode="before")
    @classmethod
    def resolve_ssh_key_path(cls, v: Any) -> Optional[Path]:
        """Resolve SSH key path relative to home directory if needed."""
        if v is None:
            return None
        if isinstance(v, str):
            if v.startswith("~/"):
                return Path.home() / v[2:]
            return Path(v)
        return v


class ExecutionConfig(BaseModel):
    """Configuration for task execution."""
    
    default_nodes: int = Field(1, ge=1, description="Default number of nodes to use")
    default_gpus_per_node: int = Field(1, ge=0, description="Default GPUs per node")
    timeout_seconds: int = Field(3600, ge=1, description="Default timeout in seconds")
    retry_attempts: int = Field(3, ge=0, description="Number of retry attempts")
    working_directory: str = Field("/tmp/grid", description="Working directory on nodes")
    environment: Dict[str, str] = Field(default_factory=dict, description="Environment variables")
    
    @field_validator("working_directory")
    @classmethod
    def ensure_absolute_path(cls, v: str) -> str:
        """Ensure working directory is an absolute path."""
        if not v.startswith("/"):
            return f"/{v}"
        return v


class LoggingConfig(BaseModel):
    """Configuration for logging."""
    
    level: str = Field("INFO", description="Log level")
    format: str = Field("json", description="Log format (json or text)")
    file_path: Optional[Path] = Field(None, description="Log file path")


class ResourceSharingConfig(BaseModel):
    """Configuration for resource sharing."""
    
    enabled: bool = Field(True, description="Enable resource sharing")
    check_interval: int = Field(60, ge=10, description="Resource check interval in seconds")
    offer_expiry: int = Field(300, ge=60, description="Resource offer expiry in seconds")
    max_offers_per_node: int = Field(5, ge=1, description="Max concurrent offers per node")
    thresholds: Dict[str, float] = Field(
        default_factory=lambda: {
            "gpu_utilization_max": 20.0,
            "gpu_memory_min_mb": 1024.0,
            "memory_percent_max": 50.0,
            "memory_min_gb": 2.0,
            "cpu_percent_max": 30.0,
            "cpu_min_cores": 1.0,
        },
        description="Resource availability thresholds"
    )


class ClusterConfig(BaseModel):
    """Main cluster configuration."""
    
    name: str = Field(..., description="Cluster name")
    nodes: List[NodeConfig] = Field(..., min_length=1, description="List of nodes")
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    resource_sharing: ResourceSharingConfig = Field(default_factory=ResourceSharingConfig)
    
    @classmethod
    def from_yaml(cls, path: Path) -> ClusterConfig:
        """Load configuration from YAML file."""
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return cls(**data)
    
    def to_yaml(self, path: Path) -> None:
        """Save configuration to YAML file."""
        with open(path, "w") as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False, indent=2)
    
    def get_node_by_name(self, name: str) -> Optional[NodeConfig]:
        """Get a node configuration by name."""
        for node in self.nodes:
            if node.name == name:
                return node
        return None
    
    def get_nodes_by_tag(self, tag: str) -> List[NodeConfig]:
        """Get all nodes with a specific tag."""
        return [node for node in self.nodes if tag in node.tags]
