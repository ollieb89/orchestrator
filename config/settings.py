from dataclasses import dataclass, field
from typing import List, Dict, Optional
import os
from pathlib import Path
import yaml

@dataclass
class SSHConfig:
    """SSH connection settings"""
    timeout: int = 10
    connect_timeout: int = 5
    max_retries: int = 3
    pool_size: int = 10
    key_file: Optional[str] = None

@dataclass
class HealthCheckConfig:
    """Health check settings"""
    timeout: int = 3
    max_workers: int = 20
    cpu_weight: float = 1.0
    gpu_weight: float = 3.0
    refresh_interval: int = 60

@dataclass
class SyncConfig:
    """Code synchronization settings"""
    exclude_patterns: List[str] = field(default_factory=lambda: [
        '.git', '__pycache__', '.env', '*.pyc', 'node_modules', '.next'
    ])
    use_checksums: bool = True
    follow_symlinks: bool = False
    max_parallel_transfers: int = 5

@dataclass
class RayConfig:
    """Ray cluster settings"""
    dashboard_port: int = 8265
    redis_port: int = 6379
    head_bind_all: bool = True
    namespace: str = "default"
    log_level: str = "info"

@dataclass
class ClusterConfig:
    """Master cluster configuration"""
    nodes: List[str] = field(default_factory=lambda: ["gpu1", "gpu2"])
    remote_root: str = "~/grid_workspace"
    local_cache_dir: str = ".grid_cache"
    ssh: SSHConfig = field(default_factory=SSHConfig)
    health_check: HealthCheckConfig = field(default_factory=HealthCheckConfig)
    sync: SyncConfig = field(default_factory=SyncConfig)
    ray: RayConfig = field(default_factory=RayConfig)

    @classmethod
    def from_yaml(cls, path: str) -> 'ClusterConfig':
        """Load config from YAML file"""
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        return cls(**data)

    @classmethod
    def from_env(cls) -> 'ClusterConfig':
        """Load config from environment variables"""
        nodes = os.getenv('GRID_NODES', 'gpu1,gpu2').split(',')
        return cls(nodes=nodes)