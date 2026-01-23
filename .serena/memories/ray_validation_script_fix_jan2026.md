# Ray Validation Script Fix

## Issue
AttributeError when running the validation script: `'ClusterConfig' object has no attribute 'ray'`

## Root Cause
The validation script was trying to access `cluster_config.ray.dashboard_port`, but the `ClusterConfig` model doesn't have a `ray` attribute. The dashboard port is a parameter passed to the `start_cluster` method, not part of the configuration model.

## Solution Implemented

### 1. Fixed Dashboard Port Access
Changed from:
```python
dashboard_port = cluster_config.ray.dashboard_port
```
To:
```python
dashboard_port = 8265  # Default dashboard port as used in CLI
```

### 2. Improved Status Parsing
Enhanced the Ray status output parsing to correctly identify running nodes:
- Check for "running" in output with multiple lines
- Look for node IDs (node_*) which indicate Ray is active
- Count the number of nodes for better status details

### 3. Better Error Messages
Updated dashboard status messages to include the port number for clarity.

## Usage
The validation script now works correctly:

```bash
# Quick health check
poetry run python scripts/validate_ray_cluster.py -c config/my-cluster.yaml

# Monitor heartbeats for 2 minutes
poetry run python scripts/validate_ray_cluster.py -c config/my-cluster.yaml --monitor 120
```

## Output
The script now correctly reports:
- Node status for all cluster nodes
- Dashboard accessibility
- Overall cluster health
- Exit code 0 for healthy clusters, 1 for issues