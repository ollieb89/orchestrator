from config.settings import ClusterConfig
from core.ssh_pool import get_pool
from core.health_check import HealthChecker
from core.sync_manager import SyncManager
from cluster.executor_optimized import OptimizedExecutor
from utils.logging import setup_logging
from utils.metrics import get_metrics

if __name__ == "__main__":
    # Setup
    setup_logging("INFO")
    metrics = get_metrics()
    
    # Load config
    config = ClusterConfig.from_yaml("config/cluster_config.yaml")
    
    # Execute
    executor = OptimizedExecutor()
    result = executor.run_distributed("python train.py --epochs 100")
    
    print(result)
