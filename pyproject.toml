# Production Scaffold - Core Components

## 1. config/settings.py

```python
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
```

## 2. core/ssh_pool.py

```python
import paramiko
import threading
import time
from typing import Tuple, Optional
from functools import lru_cache
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)

class SSHConnection:
    def __init__(self, host: str, timeout: int = 10):
        self.host = host
        self.timeout = timeout
        self.client = None
        self.last_used = time.time()
        self.command_count = 0
        self._connect()
    
    def _connect(self):
        """Establish SSH connection"""
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(self.host, timeout=self.timeout)
        logger.info(f"Connected to {self.host}")
    
    def execute(self, command: str, timeout: int = 30) -> Tuple[str, str]:
        """Execute command on remote host"""
        try:
            stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout)
            self.command_count += 1
            self.last_used = time.time()
            return stdout.read().decode().strip(), stderr.read().decode().strip()
        except Exception as e:
            logger.error(f"Command failed on {self.host}: {e}")
            raise
    
    def close(self):
        """Close SSH connection"""
        if self.client:
            self.client.close()
            logger.info(f"Closed connection to {self.host}")
    
    def is_alive(self) -> bool:
        """Check if connection is still alive"""
        try:
            self.client.exec_command("echo 'ping'")
            return True
        except:
            return False

class SSHPool:
    def __init__(self, max_size: int = 10, timeout: int = 10):
        self.pool: Dict[str, SSHConnection] = {}
        self.lock = threading.RLock()
        self.max_size = max_size
        self.timeout = timeout
    
    def get_connection(self, host: str) -> SSHConnection:
        """Get or create connection from pool"""
        with self.lock:
            if host not in self.pool:
                if len(self.pool) >= self.max_size:
                    # Evict least recently used
                    lru_host = min(self.pool, key=lambda h: self.pool[h].last_used)
                    self.pool[lru_host].close()
                    del self.pool[lru_host]
                
                self.pool[host] = SSHConnection(host, self.timeout)
            
            conn = self.pool[host]
            if not conn.is_alive():
                conn.close()
                self.pool[host] = SSHConnection(host, self.timeout)
            
            return self.pool[host]
    
    def execute(self, host: str, command: str, timeout: int = 30) -> Tuple[str, str]:
        """Execute command on host with automatic reconnection"""
        conn = self.get_connection(host)
        return conn.execute(command, timeout)
    
    def execute_all(self, hosts: list, command: str) -> Dict[str, Tuple[str, str]]:
        """Execute command on all hosts in parallel"""
        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(hosts)) as executor:
            futures = {
                executor.submit(self.execute, host, command): host 
                for host in hosts
            }
            for future in concurrent.futures.as_completed(futures):
                host = futures[future]
                try:
                    results[host] = future.result()
                except Exception as e:
                    logger.error(f"Failed on {host}: {e}")
                    results[host] = ("", str(e))
        return results
    
    def close_all(self):
        """Close all connections"""
        with self.lock:
            for host, conn in self.pool.items():
                conn.close()
            self.pool.clear()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close_all()

# Global pool instance
_pool: Optional[SSHPool] = None

def get_pool(max_size: int = 10) -> SSHPool:
    global _pool
    if _pool is None:
        _pool = SSHPool(max_size)
    return _pool
```

## 3. core/health_check.py

```python
import concurrent.futures
import subprocess
import logging
from typing import Dict, List, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class NodeHealth:
    host: str
    cpu_load: float
    gpu_memory_percent: float
    score: float
    is_healthy: bool

class HealthChecker:
    def __init__(self, timeout: int = 3, cpu_weight: float = 1.0, gpu_weight: float = 3.0):
        self.timeout = timeout
        self.cpu_weight = cpu_weight
        self.gpu_weight = gpu_weight
    
    def check_single_node(self, host: str) -> NodeHealth:
        """Check health of single node"""
        try:
            cmd = (
                "cat /proc/loadavg | awk '{print $1}' && "
                "if command -v nvidia-smi &> /dev/null; then "
                "nvidia-smi --query-gpu=memory.used,memory.total "
                "--format=csv,noheader,nounits 2>/dev/null || echo '0,0'; "
                "else echo '0,0'; fi"
            )
            
            result = subprocess.run(
                f'ssh -o ConnectTimeout={self.timeout} {host} "{cmd}"',
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout + 1
            )
            
            if result.returncode != 0:
                return NodeHealth(host, 999, 100, 999, False)
            
            lines = result.stdout.strip().split('\n')
            cpu_load = float(lines[0])
            
            gpu_memory_percent = 0
            if len(lines) > 1 and lines[1].strip() != '0,0':
                try:
                    used, total = map(int, lines[1].split(','))
                    gpu_memory_percent = (used / total * 100) if total > 0 else 0
                except:
                    pass
            
            # Score: weighted combination
            score = (cpu_load * self.cpu_weight) + (gpu_memory_percent * self.gpu_weight)
            
            return NodeHealth(
                host=host,
                cpu_load=cpu_load,
                gpu_memory_percent=gpu_memory_percent,
                score=score,
                is_healthy=score < 200
            )
        
        except Exception as e:
            logger.error(f"Health check failed for {host}: {e}")
            return NodeHealth(host, 999, 100, 999, False)
    
    def check_all_nodes(self, hosts: List[str], max_workers: int = 20) -> List[NodeHealth]:
        """Check health of all nodes in parallel"""
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, len(hosts))) as executor:
            futures = {
                executor.submit(self.check_single_node, host): host 
                for host in hosts
            }
            
            for future in concurrent.futures.as_completed(futures, timeout=self.timeout + 5):
                try:
                    health = future.result()
                    results.append(health)
                except Exception as e:
                    host = futures[future]
                    logger.error(f"Health check timeout for {host}")
                    results.append(NodeHealth(host, 999, 100, 999, False))
        
        return sorted(results, key=lambda x: x.score)
    
    def find_best_node(self, hosts: List[str]) -> Tuple[str, NodeHealth]:
        """Find healthiest node"""
        healths = self.check_all_nodes(hosts)
        healthy = [h for h in healths if h.is_healthy]
        
        if healthy:
            best = healthy[0]
        else:
            best = healths[0]
        
        logger.info(f"Selected {best.host} (score: {best.score:.2f})")
        return best.host, best
```

## 4. core/sync_manager.py

```python
import os
import hashlib
import subprocess
from typing import Set, List
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)

class SyncManager:
    def __init__(self, exclude_patterns: List[str]):
        self.exclude_patterns = exclude_patterns
        self.manifest_file = '.grid_sync_manifest'
    
    def generate_file_hash(self, filepath: str) -> str:
        """Generate MD5 hash for file"""
        md5 = hashlib.md5()
        try:
            with open(filepath, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    md5.update(chunk)
            return md5.hexdigest()
        except:
            return ""
    
    def generate_local_manifest(self) -> dict:
        """Generate manifest of local files"""
        manifest = {}
        for root, dirs, files in os.walk('.'):
            # Skip excluded patterns
            dirs[:] = [d for d in dirs if not self._should_exclude(f"{root}/{d}")]
            
            for file in files:
                filepath = os.path.join(root, file)
                if not self._should_exclude(filepath):
                    manifest[filepath] = self.generate_file_hash(filepath)
        
        return manifest
    
    def _should_exclude(self, path: str) -> bool:
        """Check if path should be excluded"""
        for pattern in self.exclude_patterns:
            if pattern in path:
                return True
        return False
    
    def get_changed_files(self, remote_manifest: dict, local_manifest: dict) -> List[str]:
        """Get list of changed files"""
        changed = []
        for filepath, local_hash in local_manifest.items():
            remote_hash = remote_manifest.get(filepath, "")
            if local_hash != remote_hash:
                changed.append(filepath)
        return changed
    
    def smart_sync(self, host: str, remote_path: str) -> None:
        """Sync only changed files"""
        # Generate local manifest
        local_manifest = self.generate_local_manifest()
        
        # Get remote manifest
        try:
            remote_manifest_cmd = f"cat {remote_path}/.grid_sync_manifest 2>/dev/null"
            result = subprocess.run(
                f'ssh {host} "{remote_manifest_cmd}"',
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            remote_manifest = json.loads(result.stdout) if result.stdout else {}
        except:
            remote_manifest = {}
        
        # Find changed files
        changed_files = self.get_changed_files(remote_manifest, local_manifest)
        
        if not changed_files:
            logger.info("No files changed, skipping sync")
            return
        
        logger.info(f"Syncing {len(changed_files)} changed files to {host}:{remote_path}")
        
        # Create list file
        with open('/tmp/grid_sync_list', 'w') as f:
            for file in changed_files:
                f.write(f"{file}\n")
        
        # Rsync only changed files
        cmd = (
            f"rsync -azP --files-from=/tmp/grid_sync_list . "
            f"{host}:{remote_path}/"
        )
        
        subprocess.run(cmd, shell=True, check=True)
        
        # Update remote manifest
        manifest_path = f"{remote_path}/.grid_sync_manifest"
        manifest_json = json.dumps(local_manifest)
        update_cmd = f'echo \'{manifest_json}\' > {manifest_path}'
        subprocess.run(f'ssh {host} "{update_cmd}"', shell=True)
        
        logger.info("Sync complete")
```

## 5. config/cluster_config.yaml

```yaml
nodes:
  - gpu1
  - gpu2

remote_root: ~/grid_workspace

ssh:
  timeout: 10
  connect_timeout: 5
  max_retries: 3
  pool_size: 10
  key_file: null

health_check:
  timeout: 3
  max_workers: 20
  cpu_weight: 1.0
  gpu_weight: 3.0
  refresh_interval: 60

sync:
  exclude_patterns:
    - .git
    - __pycache__
    - .env
    - '*.pyc'
    - node_modules
    - .next
  use_checksums: true
  follow_symlinks: false
  max_parallel_transfers: 5

ray:
  dashboard_port: 8265
  redis_port: 6379
  head_bind_all: true
  namespace: default
  log_level: info
```

## 6. tasks/batch_executor.py

```python
import ray
import time
import logging
from typing import List, Callable, Any, Dict

logger = logging.getLogger(__name__)

class BatchExecutor:
    def __init__(self, batch_size: int = 10):
        self.batch_size = batch_size
    
    def submit_batched_tasks(
        self, 
        task_func: Callable,
        task_list: List[Any],
        batch_size: Optional[int] = None
    ) -> List[Any]:
        """Submit tasks in batches to Ray"""
        batch_size = batch_size or self.batch_size
        futures = []
        
        for i in range(0, len(task_list), batch_size):
            batch = task_list[i:i + batch_size]
            batch_id = i // batch_size
            
            logger.info(f"Submitting batch {batch_id} with {len(batch)} tasks")
            
            # Submit as single Ray task
            future = task_func.remote(batch_id, batch)
            futures.append(future)
        
        # Wait for all batches
        results = ray.get(futures)
        
        # Flatten results
        flattened = []
        for batch_results in results:
            flattened.extend(batch_results)
        
        return flattened

@ray.remote(num_gpus=1)
def batch_gpu_task(batch_id: int, tasks: List[tuple]) -> List[str]:
    """Execute multiple GPU tasks in single allocation"""
    import numpy as np
    results = []
    
    logger.info(f"Batch {batch_id} starting with {len(tasks)} tasks")
    start_time = time.time()
    
    for task_id, data_size in tasks:
        A = np.random.rand(data_size, data_size)
        B = np.random.rand(data_size, data_size)
        C = np.dot(A, B)
        results.append(f"Task {task_id} in batch {batch_id} completed")
    
    elapsed = time.time() - start_time
    logger.info(f"Batch {batch_id} completed in {elapsed:.2f}s")
    return results
```

## 7. pyproject.toml

```toml
[build-system]
requires = ["setuptools>=45", "wheel", "setuptools_scm[toml]>=6.2"]
build-backend = "setuptools.build_meta"

[project]
name = "distributed-grid"
version = "0.2.0"
description = "Optimized distributed GPU cluster orchestration"
readme = "README.md"
requires-python = ">=3.9"
license = {text = "MIT"}
authors = [
    {name = "Grid Team", email = "team@grid.local"}
]
keywords = ["distributed", "gpu", "ray", "cluster", "orchestration"]

dependencies = [
    "ray[default]>=2.10.0",
    "paramiko>=3.0.0",
    "pyyaml>=6.0",
    "prometheus-client>=0.17.0",
    "python-dotenv>=1.0.0",
    "click>=8.1.0",
    "structlog>=23.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "black>=23.0",
    "isort>=5.12",
    "ruff>=0.1.0",
    "mypy>=1.0",
]

[tool.black]
line-length = 100
target-version = ['py39', 'py310', 'py311']

[tool.isort]
profile = "black"
line_length = 100

[tool.ruff]
line-length = 100
select = ["E", "F", "W", "I"]

[tool.mypy]
python_version = "3.9"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = false
```

---

**Next**: CLI interface, metrics export, and retry logic coming in next scaffold!
