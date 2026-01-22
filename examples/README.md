# Examples

This directory contains example scripts and workflows for using Distributed Grid.

## Ray Workflow Example

### `heavy_workflow.py`

A demonstration of distributed task execution using Ray. This example shows:

- How to define remote tasks with GPU requirements
- Mixing CPU and GPU tasks
- Submitting work to the cluster
- Collecting results

### Running the Example

1. First, ensure you have a Ray cluster running:
```bash
poetry run grid cluster start
```

2. Run the workflow:
```bash
poetry run python examples/heavy_workflow.py
```

### Expected Output

```
Connected to Ray Cluster!
Available resources: {'CPU': 8, 'GPU': 2, ...}

--- Submitting Workflows ---

--- GPU Results ---
Task 0 completed on gpu1 in 2.34s
Task 1 completed on gpu2 in 2.31s
Task 2 completed on gpu1 in 2.29s
Task 3 completed on gpu2 in 2.33s

--- CPU Results ---
Processed Data_Chunk_0 on cpu1
Processed Data_Chunk_1 on cpu2
...
```

## Customizing the Example

You can modify the workflow to:

- Change the matrix size for computation intensity
- Add your own model inference code
- Adjust the number of parallel tasks
- Add different types of remote functions

## Best Practices

1. Always specify resource requirements (`num_gpus`, `num_cpus`)
2. Use `ray.get()` sparingly - it blocks until completion
3. Consider using `ray.wait()` for streaming results
4. Handle exceptions properly in remote functions
