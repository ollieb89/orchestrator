# Process Offloading Guide

## Overview

The process offloading feature allows you to migrate running processes from the master node to worker nodes with available resources. This helps balance the cluster load and utilize idle resources.

## Commands

### Scan for Offloadable Processes

```bash
# Scan all nodes
grid offload scan

# Scan specific node
grid offload scan -n gpu1

# JSON output
grid offload scan --format json
```

### Offload a Process

```bash
# Offload specific PID (auto-selects target)
grid offload execute 12345

# Offload to specific node
grid offload execute 12345 --target-node gpu1

# With custom runtime environment
grid offload execute 12345 --runtime-env '{"env_vars": {"CUDA_VISIBLE_DEVICES": "0"}}'
```

### Check Status

```bash
# View offloading statistics and active tasks
grid offload status
```

### Cancel Offloading

```bash
# Cancel active task
grid offload cancel offload_1701234567_12345
```

## How It Works

1. **Detection**: The system scans for processes that:
   - Use significant CPU, memory, or GPU resources
   - Are long-running (> 1 minute)
   - Are not critical system processes
   - Match known patterns (training, inference, data processing)

2. **Matching**: Finds suitable target nodes based on:
   - Available resources (CPU cores, memory, GPU)
   - Resource requirements of the process
   - Network considerations

3. **Migration**: Uses Ray jobs to:
   - Capture process state (environment, working directory)
   - Submit as a Ray job to the target node
   - Monitor execution progress

## Process Types

The system classifies processes into:
- **Training**: ML model training jobs
- **Inference**: Model serving/prediction
- **Data Processing**: ETL, analytics
- **Compute Intensive**: Heavy CPU/GPU computation
- **Batch Jobs**: Scheduled/automated tasks
- **Interactive**: User sessions (not offloaded)
- **Daemon**: System services (not offloaded)

## Configuration

Resource thresholds for offloading detection (configurable):
- GPU utilization < 20%
- Memory usage < 50%
- CPU usage < 30%
- Minimum GPU memory: 1GB
- Minimum memory: 2GB
- Minimum CPU cores: 1

## Examples

### Offload a Training Job

```bash
# Find the training process
grid offload scan | grep train

# Offload it
grid offload execute 23456

# Monitor progress
grid offload status
```

### Batch Offload Multiple Processes

```bash
# Get list in JSON format
grid offload scan --format json > processes.json

# Extract PIDs and offload
jq -r '.[].pid' processes.json | xargs -I {} grid offload execute {}
```

## Limitations

1. Process state capture is best-effort
2. Network-dependent processes may fail
3. GPU processes have higher migration complexity
4. Interactive sessions are not offloaded
5. Requires Ray dashboard to be accessible

## Troubleshooting

### Process Not Found
- Check if the process is still running: `ps aux | grep <PID>`
- Verify it's resource-intensive enough
- Use `grid offload scan` to see eligible processes

### Offloading Failed
- Check Ray dashboard is running: `http://localhost:8265`
- Verify target node has sufficient resources
- Check logs for detailed error messages

### Performance Issues
- Monitor network bandwidth between nodes
- Consider data locality before offloading
- Use `--capture-state=False` for stateless processes
