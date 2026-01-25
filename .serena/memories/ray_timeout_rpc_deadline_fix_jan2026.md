# Ray RPC Deadline Timeout Fix - January 2026

## Problem
Worker nodes failing to start with "RPC error: Deadline Exceeded" during Ray cluster startup.

```
✗ Failed to start worker gpu1: 2026-01-24 03:01:02,212 - INFO - Failed to auto-detect TPU
...
2026-01-24 03:01:33,220 INFO node.py:362 -- Failed to get node info b'RPC error: Deadline Exceeded'
Exception: The current node timed out during startup.
```

## Root Causes

1. **Insufficient GCS Initialization Time**: Workers were attempting to connect before GCS server fully started
2. **RPC Timeout During Startup**: Worker nodes hitting RPC deadline when negotiating with head node
3. **Concurrent Worker Startup**: All workers starting simultaneously overwhelming the GCS server ("thundering herd")
4. **Insufficient SSH Command Timeout**: Ray startup was taking > 60 seconds

## Solution Implemented

### File: `src/distributed_grid/cluster/__init__.py`

#### Change 1: Increased GCS Initialization Wait Time
**Lines 125-127**: Increased initial head node wait from 30s → 45s
- Gives Ray's GCS server more time to fully initialize
- Increased `_wait_for_gcs_ready()` retries from 15 → 20

#### Change 2: Extended SSH Command Timeouts
- **Head node startup**: 60s → 120s (Line 188)
- **Worker node startup**: 60s → 120s (Line 311)
- Reason: Ray startup with all environment variables can take 60-90 seconds

#### Change 3: Added GRPC & RPC Configuration
Added environment variables to both head and worker node startup:
```bash
RAY_grpc_keepalive_time_ms=30000        # GRPC keepalive every 30 seconds
RAY_grpc_keepalive_timeout_ms=20000     # GRPC keepalive timeout
RAY_rpc_server_max_message_length=536870912  # 512MB max message
RAY_grpc_max_send_message_length=536870912   # 512MB max send
RAY_grpc_max_recv_message_length=536870912   # 512MB max recv
```

These settings prevent RPC deadline violations by:
- Enabling GRPC keepalive to detect stale connections
- Allowing larger message sizes for Ray metadata exchange
- Preventing premature timeout during protocol handshake

#### Change 4: Sequential Worker Startup
**Lines 252-263**: Changed from parallel to sequential worker startup with 10-second delays
- Prevents GCS server overload from multiple simultaneous connection attempts
- Ensures each worker fully connects before next worker starts
- More reliable cluster formation

### Environment Variable Summary

Both head and worker nodes now use:
```bash
RAY_backend_log_level=debug
RAY_heartbeat_timeout_ms=180000          # 180 seconds (3 minutes)
RAY_num_heartbeat_timeout_periods=20     # Allow 20 missed heartbeats
RAY_health_check_initial_delay_ms=30000  # 30 seconds initial delay
RAY_health_check_period_ms=30000         # Check every 30 seconds
RAY_health_check_timeout_ms=30000        # 30 seconds timeout
RAY_gcs_server_request_timeout_seconds_ms=300000  # 300 seconds
RAY_timeout_ms=300000                    # 300 seconds general timeout
RAY_raylet_death_check_interval_ms=10000 # Check every 10 seconds
RAY_node_manager_timeout_ms=180000       # Node manager timeout
RAY_gcs_rpc_server_reconnect_timeout_s=300  # GCS RPC reconnect
RAY_grpc_keepalive_time_ms=30000         # NEW: GRPC keepalive
RAY_grpc_keepalive_timeout_ms=20000      # NEW: GRPC timeout
RAY_rpc_server_max_message_length=536870912  # NEW: 512MB messages
RAY_grpc_max_send_message_length=536870912   # NEW: 512MB send
RAY_grpc_max_recv_message_length=536870912   # NEW: 512MB recv
```

## Deployment Steps

### 1. Stop Current Cluster
```bash
poetry run grid cluster stop -c config/my-cluster.yaml
```

### 2. Deploy Updated Code
The code changes are already in place. Verify:
```bash
grep -n "RAY_grpc_keepalive_time_ms" src/distributed_grid/cluster/__init__.py
```

### 3. Restart Cluster
```bash
poetry run grid cluster start -c config/my-cluster.yaml
```

Expected output:
```
Starting Ray cluster...
Head node started at 192.168.1.100:6399
Waiting for head node to be fully ready...
Waiting for GCS to be ready at 192.168.1.100:6399...
✓ GCS is ready at 192.168.1.100:6399
✓ Worker gpu1 connected
✓ Worker gpu2 connected
✓ Ray cluster is active!
Dashboard: http://localhost:8265
```

### 4. Validate Cluster Health
```bash
poetry run python scripts/validate_ray_cluster.py -c config/my-cluster.yaml

# Monitor for 2 minutes
poetry run python scripts/validate_ray_cluster.py -c config/my-cluster.yaml --monitor 120
```

## What Changed & Why

| Issue | Original | Fixed | Reason |
|-------|----------|-------|--------|
| GCS init wait | 30s | 45s | Ray GCS needs 30-40s to fully initialize |
| SSH timeout (head) | 60s | 120s | Ray startup with env vars takes 60-90s |
| SSH timeout (worker) | 60s | 120s | Same as head node |
| Worker startup | Parallel (all at once) | Sequential + 10s delay | Prevents GCS overload |
| RPC keepalive | Not set | Every 30s | Detects stale connections |
| GRPC message size | Default | 512MB | Allows larger metadata |
| GCS readiness check | 15 attempts | 20 attempts | More tolerance for slow startup |

## Validation Checklist

After restarting cluster:
- [ ] Head node starts successfully
- [ ] All workers connect without timeout errors
- [ ] Dashboard accessible at http://localhost:8265
- [ ] `ray status` shows all nodes as healthy
- [ ] No "RPC error: Deadline Exceeded" in logs
- [ ] No "Failed to auto-detect TPU" errors (these are harmless but will still appear)

## Troubleshooting

### If errors persist:
1. Check network connectivity between nodes
2. Monitor Ray logs: `ssh gpu1 "tail -f /tmp/ray/*/logs/raylet.err"`
3. Increase timeouts further if network is very slow
4. Check GCS logs on head: `ssh gpu-master "tail -f /tmp/ray/*/logs/gcs_server.log"`

### Fine-tuning for Slow Networks
If timeouts still occur, increase these values:
```bash
RAY_heartbeat_timeout_ms=300000          # Up to 5 minutes
RAY_health_check_period_ms=60000         # Up to 1 minute
RAY_gcs_server_request_timeout_seconds_ms=600000  # 10 minutes
```

## Files Modified
- `src/distributed_grid/cluster/__init__.py` - Head/worker node startup, GCS wait time, worker startup strategy

## Related Documentation
- [ray_heartbeat_fix.md](ray_heartbeat_fix.md) - Original heartbeat timeout fix
- [ray_gcs_startup_timeout_fix_jan2026.md](ray_gcs_startup_timeout_fix_jan2026.md) - Earlier GCS fix
