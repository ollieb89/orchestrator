# Ray Cluster Fixes & Port Migration (2026-01-23)

## Problem
- Ray dashboard showed workers as DEAD due to missed heartbeats
- Port conflict: client_server and node_manager both tried to use port 10001
- Default Ray head port 6379 was already in use by another service

## Solutions Applied
### 1. Fixed port conflicts in RayClusterManager
- Head node: added `--ray-client-server-port=10003` (separate from node_manager_port=10001)
- Worker nodes: added `--ray-client-server-port=10003` to avoid same conflict
- Kept deterministic ports for networking:
  - node_manager_port=10001
  - object_manager_port=10002
  - min/max_worker_port=11000-11100
  - ray_client_server_port=10003

### 2. Changed default Ray head port
- CLI default: `grid cluster start --port` changed from 6379 to 6399
- RayClusterManager.start_cluster() default changed from 6379 to 6399
- Override still available via `--port` flag

## Current Configuration
- Head node: 192.168.1.100:6399
- Dashboard: http://localhost:8265
- Workers: gpu1 (192.168.1.101), gpu2 (192.168.1.102) connect successfully
- All nodes show as ALIVE in Ray dashboard

## Verification Commands
```bash
# Start cluster (uses 6399 by default)
poetry run grid cluster start -c config/my-cluster.yaml --dashboard-port 8265

# Check cluster status
poetry run grid execute -c config/my-cluster.yaml -n gpu-master "~/distributed_cluster_env/bin/ray status"

# Stop cluster
poetry run grid cluster stop -c config/my-cluster.yaml
```

## Files Modified
- src/distributed_grid/cluster/__init__.py: port fixes and defaults
- src/distributed_grid/cli.py: CLI default port change

## Notes
- Fixed ports make cluster networking predictable and avoid firewall issues with ephemeral ports
- Workers now stay ALIVE consistently after startup
- No changes needed to config/my-cluster.yaml for these fixes