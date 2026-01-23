# Ray Cluster Heartbeat Fix and Monitoring

## Issue

The Ray dashboard was showing "Unexpected termination: health check failed due to missing too many heartbeats" error, causing nodes to be marked as unhealthy and disrupting cluster operations.

## Root Cause

Default Ray heartbeat timeouts were too aggressive for the cluster network environment:
- Default heartbeat timeout: 30 seconds
- Default missed heartbeat threshold: 5 periods
- This caused nodes to be marked dead during normal network latency

## Solution Implemented

### 1. Increased Heartbeat Timeouts

Updated Ray cluster configuration in `/src/distributed_grid/cluster/__init__.py`:

```bash
RAY_heartbeat_timeout_ms=180000          # 180 seconds (3 minutes)
RAY_num_heartbeat_timeout_periods=20     # Allow 20 missed heartbeats
RAY_health_check_initial_delay_ms=30000  # 30 seconds initial delay
RAY_health_check_period_ms=30000         # Check every 30 seconds
RAY_health_check_timeout_ms=30000        # 30 seconds timeout for health checks
RAY_gcs_server_request_timeout_seconds_ms=300000  # 300 seconds GCS timeout
RAY_timeout_ms=300000                    # 300 seconds general timeout
RAY_raylet_death_check_interval_ms=10000 # Check every 10 seconds
RAY_node_manager_timeout_ms=180000       # Node manager timeout
RAY_gcs_rpc_server_reconnect_timeout_s=300 # GCS RPC reconnect timeout
```

### 2. Remote Dashboard Access

Configured Ray dashboard to accept remote connections:
```bash
--dashboard-host=0.0.0.0
--dashboard-port=8265
```

### 3. Heartbeat Monitoring Tool

Created a monitoring script `/scripts/monitor_heartbeat.py` that:
- Continuously monitors cluster heartbeat health
- Provides real-time status display
- Supports automatic healing of failed nodes
- Sends alerts when nodes exceed failure threshold

## Usage

### Check Cluster Health
```bash
# Quick health check
poetry run python scripts/validate_ray_cluster.py -c config/my-cluster.yaml

# Monitor for 2 minutes
poetry run python scripts/validate_ray_cluster.py -c config/my-cluster.yaml --monitor 120
```

### Monitor Heartbeats
```bash
# Basic monitoring (checks every 30 seconds)
poetry run grid offload monitor

# Custom monitoring
poetry run grid offload monitor --interval 10 --duration 300

# Enable auto-healing
poetry run grid offload monitor --auto-heal

# Adjust alert threshold
poetry run grid offload monitor --alert-threshold 5
```

### Access Dashboard Remotely
```bash
# Forward dashboard port
ssh -L 8265:localhost:8265 gpu-master

# Access in browser
http://localhost:8265
```

## Validation

After applying the fix:
1. All nodes remain stable with no heartbeat errors
2. Dashboard accessible from remote locations
3. Cluster survives network latency spikes
4. Automatic recovery from temporary disconnections

## Troubleshooting

### If Heartbeat Errors Persist

1. **Check Network Connectivity**
   ```bash
   ping gpu1
   ping gpu2
   ```

2. **Verify Ray Processes**
   ```bash
   ssh gpu-master "ps aux | grep ray"
   ssh gpu1 "ps aux | grep ray"
   ssh gpu2 "ps aux | grep ray"
   ```

3. **Check Ray Logs**
   ```bash
   ssh gpu-master "tail -f /tmp/ray/session_*/logs/dashboard.err"
   ssh gpu1 "tail -f /tmp/ray/session_*/logs/raylet.err"
   ```

4. **Restart Cluster with Increased Timeouts**
   ```bash
   poetry run python -m distributed_grid.cli cluster stop -c config/my-cluster.yaml
   poetry run python -m distributed_grid.cli cluster start -c config/my-cluster.yaml
   ```

### Fine-tuning Timeouts

If issues persist in high-latency environments, increase timeouts further:
- `RAY_heartbeat_timeout_ms`: Up to 600000 (10 minutes)
- `RAY_num_heartbeat_timeout_periods`: Up to 30
- `RAY_health_check_period_ms`: Up to 60000 (1 minute)

## Best Practices

1. **Monitor Regularly**: Use the heartbeat monitor for early detection
2. **Set Up Alerts**: Configure monitoring to notify on failures
3. **Document Network**: Understand your network latency patterns
4. **Test Recovery**: Regularly test cluster recovery from failures
5. **Backup Config**: Keep cluster configuration version controlled

## Related Files

- `/src/distributed_grid/cluster/__init__.py` - Ray cluster startup configuration
- `/scripts/validate_ray_cluster.py` - Cluster health validation
- `/scripts/monitor_heartbeat.py` - Heartbeat monitoring tool
- `/config/my-cluster.yaml` - Cluster node configuration
