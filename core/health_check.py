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
