import os
import socket
import time

import ray

# --- CONNECT TO CLUSTER ---
# This looks for the cluster we started with the manager script.
# We connect to the "local" head node, which routes traffic to the workers.
ray.init(address="auto")

print("Connected to Ray Cluster!")
print(f"Available resources: {ray.available_resources()}")

# --- DEFINE REMOTE TASKS ---


# By adding @ray.remote, this function becomes a distributable task.
# num_gpus=1 tells the system: "Only run this where a GPU is available"
@ray.remote(num_gpus=1)
def heavy_gpu_task(task_id, data_size):
    import numpy as np

    host = socket.gethostname()
    print(f"Task {task_id} starting on {host}...")

    # Simulate heavy work (Matrix Multiplication)
    # If you have PyTorch/Tensorflow installed, you would put your model inference here.
    start_time = time.time()

    # Create large random matrices
    A = np.random.rand(data_size, data_size)
    B = np.random.rand(data_size, data_size)

    # Heavy computation
    C = np.dot(A, B)

    duration = time.time() - start_time
    return f"Task {task_id} completed on {host} in {duration:.2f}s"


@ray.remote
def cpu_preprocessing(data):
    # This runs on any available CPU core in the cluster
    host = socket.gethostname()
    return f"Processed {data} on {host}"


# --- MAIN WORKFLOW ---
def run_workflow():
    print("\n--- Submitting Workflows ---\n")

    # 1. Launch 4 heavy tasks simultaneously.
    # Even though you might only have 2 GPUs remote, Ray queues them automatically.
    # As soon as gpu1 finishes task 0, it will pick up task 2, etc.
    futures = [heavy_gpu_task.remote(i, 2000) for i in range(4)]

    # 2. Launch some CPU tasks mixed in
    cpu_futures = [cpu_preprocessing.remote(f"Data_Chunk_{i}") for i in range(5)]

    # 3. Wait for results
    # ray.get() blocks until the computation is done and returns the result across the network.
    results = ray.get(futures)
    cpu_results = ray.get(cpu_futures)

    print("\n--- GPU Results ---")
    for res in results:
        print(res)

    print("\n--- CPU Results ---")
    for res in cpu_results:
        print(res)


if __name__ == "__main__":
    run_workflow()
