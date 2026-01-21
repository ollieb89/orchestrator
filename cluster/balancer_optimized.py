import sys
import json
from typing import Optional
import logging
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import ClusterConfig
from core.health_check import HealthChecker
from utils.metrics import get_metrics
import time

logger = logging.getLogger(__name__)

def get_config() -> ClusterConfig:
    """Load cluster configuration"""
    config_path = Path(__file__).parent.parent / "config" / "cluster_config.yaml"
    return ClusterConfig.from_yaml(str(config_path))

def find_best_node() -> Optional[str]:
    """Find healthiest node with parallel health checks"""
    config = get_config()
    metrics = get_metrics()
    
    start_time = time.time()
    
    checker = HealthChecker(
        timeout=config.health_check.timeout,
        cpu_weight=config.health_check.cpu_weight,
        gpu_weight=config.health_check.gpu_weight
    )
    
    # Parallel health checks
    healths = checker.check_all_nodes(
        config.nodes,
        max_workers=config.health_check.max_workers
    )
    
    elapsed = time.time() - start_time
    metrics.node_selection_time.observe(elapsed)
    
    # Record health scores
    for health in healths:
        metrics.record_node_health(health.host, health.score)
    
    # Return best healthy node
    healthy = [h for h in healths if h.is_healthy]
    if healthy:
        return healthy[0].host
    elif healths:
        logger.warning("No healthy nodes found, using least loaded")
        return healths[0].host
    
    return None

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    best = find_best_node()
    if best:
        print(best)
        sys.exit(0)
    else:
        print("Error: No nodes available", file=sys.stderr)
        sys.exit(1)
