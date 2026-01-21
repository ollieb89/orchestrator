import ray
import time
import logging
from typing import List, Callable, Any, Dict, Optional

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
