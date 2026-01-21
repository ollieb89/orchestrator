import subprocess
import logging
import sys
import shlex
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.ssh_pool import get_pool
from core.sync_manager import SyncManager
from core.health_check import HealthChecker
from config.settings import ClusterConfig
from utils.retry import retry, RetryConfig
from utils.metrics import get_metrics
import time

logger = logging.getLogger(__name__)

class OptimizedExecutor:
    def __init__(self):
        self.config = ClusterConfig.from_yaml(
            str(Path(__file__).parent.parent / "config" / "cluster_config.yaml")
        )
        self.ssh_pool = get_pool(self.config.ssh.pool_size)
        self.sync_manager = SyncManager(self.config.sync.exclude_patterns)
        self.metrics = get_metrics()

    def _build_remote_shell_command(self, remote_path: str, command: str) -> str:
        grid_env = f"{self.config.remote_root}/grid_env/bin/activate"
        remote_cmd = (
            "export PATH=~/.npm-global/bin:$PATH; "
            f"source {shlex.quote(grid_env)}; "
            f"cd {shlex.quote(remote_path)}; "
            f"{command}"
        )
        return remote_cmd

    @retry(RetryConfig(max_retries=3, initial_delay=1.0))
    def execute(self, host: str, command: str, remote_path: str, port: Optional[int] = None) -> str:
        """Execute command on remote host with retry logic"""
        logger.info(f"Executing on {host}: {command}")
        
        # Smart sync
        logger.info(f"Syncing to {host}:{remote_path}")
        sync_start = time.time()
        self.sync_manager.smart_sync(host, remote_path)
        self.metrics.sync_duration.labels(node=host).observe(
            time.time() - sync_start
        )
        
        # Execute
        logger.info(f"Running command on {host}")
        if port is not None:
            remote_cmd = self._build_remote_shell_command(remote_path, command)
            result = subprocess.run(
                [
                    "ssh",
                    "-t",
                    "-L",
                    f"{int(port)}:localhost:{int(port)}",
                    host,
                    "bash",
                    "-lc",
                    remote_cmd,
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or "SSH execution failed")
            stdout, stderr = result.stdout.strip(), result.stderr.strip()
        else:
            stdout, stderr = self.ssh_pool.execute(
                host,
                f"cd {remote_path} && {command}",
                timeout=300
            )
        
        if stderr:
            logger.warning(f"Stderr from {host}: {stderr}")
        
        return stdout

    def run_distributed(self, command: str, port: Optional[int] = None) -> str:
        """Find best node and execute"""
        # Find best node
        checker = HealthChecker(
            cpu_weight=self.config.health_check.cpu_weight,
            gpu_weight=self.config.health_check.gpu_weight
        )
        
        best_node, health = checker.find_best_node(self.config.nodes)
        logger.info(f"Selected {best_node} (score: {health.score:.2f})")
        
        # Execute
        remote_path = f"{self.config.remote_root}/{Path.cwd().name}"
        result = self.execute(best_node, command, remote_path, port=port)
        
        return result

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Execute command on best cluster node")
    parser.add_argument("command", nargs='+', help="Command to execute")
    parser.add_argument("-p", "--port", type=int, help="Port to forward")
    args = parser.parse_args()
    
    command = ' '.join(args.command)
    
    logging.basicConfig(level=logging.INFO)
    
    executor = OptimizedExecutor()
    
    try:
        result = executor.run_distributed(command, port=args.port)
        print(result)
    except Exception as e:
        logger.error(f"Execution failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
