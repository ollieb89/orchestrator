"""Examples of Ray task distribution patterns for the orchestrator."""

import ray
import asyncio
from typing import List, Dict, Any
from distributed_grid.orchestration.intelligent_scheduler import (
    IntelligentScheduler,
    SchedulingRequest,
    SchedulingStrategy,
    ResourceRequirement,
    TaskPriority,
)
from distributed_grid.monitoring.resource_metrics import ResourceMetricsCollector
from distributed_grid.orchestration.resource_sharing_manager import ResourceSharingManager
from distributed_grid.config import ClusterConfig


async def example_spread_strategy():
    """Example: Spread tasks across all available nodes."""
    
    # Create Ray remote function with SPREAD strategy
    @ray.remote
    def simple_task(task_id: int) -> Dict[str, Any]:
        """Simple task that can run on any node."""
        import socket
        import time
        
        node_ip = socket.gethostbyname(socket.gethostname())
        start_time = time.time()
        
        # Simulate some work
        result = sum(i * i for i in range(1000))
        
        return {
            "task_id": task_id,
            "node_ip": node_ip,
            "execution_time": time.time() - start_time,
            "result": result,
        }
    
    print("=== SPREAD Strategy Example ===")
    
    # Submit 100 tasks with SPREAD strategy
    refs = []
    for i in range(100):
        # Use SPREAD scheduling strategy to distribute across nodes
        remote_fn = simple_task.options(scheduling_strategy="SPREAD")
        refs.append(remote_fn.remote(i))
    
    # Wait for all tasks to complete
    results = ray.get(refs)
    
    # Count tasks per node
    node_counts = {}
    for result in results:
        node_ip = result["node_ip"]
        node_counts[node_ip] = node_counts.get(node_ip, 0) + 1
    
    print("Task distribution across nodes:")
    for node_ip, count in node_counts.items():
        print(f"  {node_ip}: {count} tasks")
    
    return results


async def example_node_specific_placement():
    """Example: Place tasks on specific nodes."""
    
    @ray.remote(num_gpus=1)
    def gpu_task(task_id: int) -> Dict[str, Any]:
        """GPU-intensive task."""
        import torch
        import socket
        
        node_ip = socket.gethostbyname(socket.gethostname())
        
        # Simulate GPU work
        if torch.cuda.is_available():
            device = torch.device("cuda")
            x = torch.randn(1000, 1000, device=device)
            result = torch.matmul(x, x.t()).sum().item()
        else:
            result = 0
        
        return {
            "task_id": task_id,
            "node_ip": node_ip,
            "gpu_available": torch.cuda.is_available(),
            "result": result,
        }
    
    print("\n=== Node-Specific Placement Example ===")
    
    # Submit tasks to specific nodes
    refs = []
    
    # Submit to gpu1 (192.168.1.101)
    for i in range(5):
        remote_fn = gpu_task.options(resources={"node:192.168.1.101": 0.001})
        refs.append(remote_fn.remote(i))
    
    # Submit to gpu2 (192.168.1.102)
    for i in range(5, 10):
        remote_fn = gpu_task.options(resources={"node:192.168.1.102": 0.001})
        refs.append(remote_fn.remote(i))
    
    # Wait for completion
    results = ray.get(refs)
    
    # Display results
    for result in results:
        print(f"Task {result['task_id']} ran on {result['node_ip']} (GPU: {result['gpu_available']})")
    
    return results


async def example_intelligent_scheduler():
    """Example: Using the intelligent scheduler for task placement."""
    
    # Initialize scheduler components (simplified example)
    cluster_config = ClusterConfig(
        nodes=[
            # This would be loaded from your config file
        ]
    )
    
    print("\n=== Intelligent Scheduler Example ===")
    
    # Example scheduling requests with different strategies
    
    # 1. SPREAD strategy for CPU tasks
    cpu_request = SchedulingRequest(
        task_id="cpu_batch_1",
        requirements=ResourceRequirement(cpu_count=1.0, memory_mb=2048),
        strategy=SchedulingStrategy.SPREAD,
        priority=TaskPriority.NORMAL,
    )
    
    # 2. PERFORMANCE_OPTIMIZED for GPU tasks
    gpu_request = SchedulingRequest(
        task_id="gpu_training_1",
        requirements=ResourceRequirement(cpu_count=2.0, memory_mb=8192, gpu_count=1),
        strategy=SchedulingStrategy.PERFORMANCE_OPTIMIZED,
        priority=TaskPriority.HIGH,
    )
    
    # 3. NODE_SPECIFIC for targeted placement
    specific_request = SchedulingRequest(
        task_id="specific_node_1",
        requirements=ResourceRequirement(cpu_count=1.0, memory_mb=1024),
        strategy=SchedulingStrategy.NODE_SPECIFIC,
        preferences={"target_node": "gpu1"},
        priority=TaskPriority.NORMAL,
    )
    
    # 4. LOAD_BALANCED for even distribution
    balanced_request = SchedulingRequest(
        task_id="balanced_batch_1",
        requirements=ResourceRequirement(cpu_count=0.5, memory_mb=1024),
        strategy=SchedulingStrategy.LOAD_BALANCED,
        priority=TaskPriority.LOW,
    )
    
    requests = [cpu_request, gpu_request, specific_request, balanced_request]
    
    print("Scheduling requests created:")
    for req in requests:
        print(f"  {req.task_id}: {req.strategy} - CPU:{req.requirements.cpu_count}, "
              f"MEM:{req.requirements.memory_mb}MB, GPU:{req.requirements.gpu_count}")
    
    # Note: In real usage, you would call:
    # decision = await scheduler.schedule_task(request)
    # print(f"Task {req.task_id} scheduled on {decision.node_id}")
    
    return requests


async def example_gpu_workload_distribution():
    """Example: Distribute GPU workloads across available GPUs."""
    
    @ray.remote(num_gpus=1)
    def training_step(batch_id: int, data_size: int = 1000) -> Dict[str, Any]:
        """Simulate a training step on GPU."""
        import torch
        import time
        import socket
        
        node_ip = socket.gethostbyname(socket.gethostname())
        start_time = time.time()
        
        if torch.cuda.is_available():
            device = torch.device("cuda")
            
            # Simulate training work
            x = torch.randn(data_size, 100, device=device)
            y = torch.randn(data_size, 1, device=device)
            
            # Simple forward pass
            for _ in range(10):
                output = torch.mm(x, x.t())
                loss = (output - y).sum()
            
            torch.cuda.synchronize()
        else:
            device = "cpu"
            x = torch.randn(data_size, 100)
            loss = x.sum()
        
        return {
            "batch_id": batch_id,
            "node_ip": node_ip,
            "device": str(device),
            "execution_time": time.time() - start_time,
            "data_size": data_size,
        }
    
    print("\n=== GPU Workload Distribution Example ===")
    
    # Submit training steps - Ray will automatically distribute across GPUs
    refs = []
    for i in range(6):  # Submit 6 tasks, should distribute across 3 GPUs
        refs.append(training_step.remote(i, data_size=2000))
    
    # Wait for completion
    results = ray.get(refs)
    
    # Analyze distribution
    gpu_usage = {}
    for result in results:
        node = result["node_ip"]
        device = result["device"]
        key = f"{node}:{device}"
        gpu_usage[key] = gpu_usage.get(key, 0) + 1
        print(f"Batch {result['batch_id']}: {node} ({device}) - {result['execution_time']:.2f}s")
    
    print("\nGPU utilization:")
    for gpu, count in gpu_usage.items():
        print(f"  {gpu}: {count} tasks")
    
    return results


async def example_mixed_workload():
    """Example: Mix of different workload types with appropriate placement."""
    
    # CPU-intensive task
    @ray.remote
    def cpu_intensive_task(task_id: int) -> Dict[str, Any]:
        """CPU-intensive computation."""
        import socket
        import time
        
        node_ip = socket.gethostbyname(socket.gethostname())
        start_time = time.time()
        
        # CPU-intensive work
        result = []
        for i in range(100000):
            result.append(i * i * i)
        
        return {
            "task_id": task_id,
            "node_ip": node_ip,
            "type": "cpu_intensive",
            "execution_time": time.time() - start_time,
        }
    
    # Memory-intensive task
    @ray.remote
    def memory_intensive_task(task_id: int) -> Dict[str, Any]:
        """Memory-intensive computation."""
        import socket
        import time
        
        node_ip = socket.gethostbyname(socket.gethostname())
        start_time = time.time()
        
        # Memory-intensive work
        large_data = [list(range(10000)) for _ in range(100)]
        result = sum(sum(row) for row in large_data)
        
        return {
            "task_id": task_id,
            "node_ip": node_ip,
            "type": "memory_intensive",
            "execution_time": time.time() - start_time,
            "result": result,
        }
    
    # GPU task
    @ray.remote(num_gpus=1)
    def gpu_task(task_id: int) -> Dict[str, Any]:
        """GPU computation."""
        import torch
        import socket
        import time
        
        node_ip = socket.gethostbyname(socket.gethostname())
        start_time = time.time()
        
        if torch.cuda.is_available():
            device = torch.device("cuda")
            x = torch.randn(5000, 5000, device=device)
            result = torch.mm(x, x.t()).sum().item()
        else:
            result = 0
        
        return {
            "task_id": task_id,
            "node_ip": node_ip,
            "type": "gpu",
            "execution_time": time.time() - start_time,
            "result": result,
        }
    
    print("\n=== Mixed Workload Example ===")
    
    # Submit different types of tasks with appropriate strategies
    refs = []
    
    # CPU tasks with SPREAD strategy
    for i in range(10):
        remote_fn = cpu_intensive_task.options(scheduling_strategy="SPREAD")
        refs.append(remote_fn.remote(f"cpu_{i}"))
    
    # Memory tasks with LOAD_BALANCED
    for i in range(5):
        remote_fn = memory_intensive_task.options(
            scheduling_strategy="LOAD_BALANCED",
            num_cpus=2.0,
        )
        refs.append(remote_fn.remote(f"mem_{i}"))
    
    # GPU tasks (automatically placed on GPU nodes)
    for i in range(3):
        refs.append(gpu_task.remote(f"gpu_{i}"))
    
    # Wait for all tasks
    results = ray.get(refs)
    
    # Analyze distribution
    distribution = {}
    for result in results:
        node = result["node_ip"]
        task_type = result["type"]
        if node not in distribution:
            distribution[node] = {}
        distribution[node][task_type] = distribution[node].get(task_type, 0) + 1
    
    print("\nTask distribution by node and type:")
    for node, types in distribution.items():
        print(f"  {node}:")
        for task_type, count in types.items():
            print(f"    {task_type}: {count} tasks")
    
    return results


# Main execution
if __name__ == "__main__":
    # Initialize Ray
    ray.init(address="ray://192.168.1.100:10001")
    
    try:
        # Run examples
        asyncio.run(example_spread_strategy())
        asyncio.run(example_node_specific_placement())
        asyncio.run(example_intelligent_scheduler())
        asyncio.run(example_gpu_workload_distribution())
        asyncio.run(example_mixed_workload())
        
    finally:
        ray.shutdown()
