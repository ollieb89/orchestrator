# Ray Dashboard Heartbeat Fix

## Issue
Ray dashboard showing "Unexpected termination: health check failed due to missing too many heartbeats"

## Root Cause
Default Ray heartbeat timeouts were too aggressive for the cluster network environment, causing nodes to be marked as unhealthy when heartbeats were delayed.

## Solution Implemented

### 1. Updated Ray Cluster Configuration
Added Ray environment variables to both head and worker node startup commands in `/src/distributed_grid/cluster/__init__.py`:

```bash
RAY_backend_log_level=info
RAY_heartbeat_timeout_ms=30000          # 30 seconds (increased from default)
RAY_num_heartbeat_timeout_periods=5     # Allow 5 missed heartbeats
RAY_health_check_initial_delay_ms=5000  # 5 seconds initial delay
RAY_health_check_period_ms=10000        # Check every 10 seconds
RAY_health_check_timeout_ms=5000        # 5 seconds timeout for health checks
RAY_gcs_server_request_timeout_seconds_ms=60000  # 60 seconds GCS timeout
RAY_timeout_ms=60000                    # 60 seconds general timeout
```

### 2. Added Configuration Options
Extended `RayConfig` in `/config/settings.py` with heartbeat-related settings to make them configurable.

### 3. Validation Script
Created `/scripts/validate_ray_cluster.py` to:
- Check cluster health
- Monitor heartbeats
- Validate dashboard accessibility
- Provide detailed status reporting

## Usage

### Restart the cluster with new settings:
```bash
poetry run python -m distributed_grid.cli cluster stop -c config/my-cluster.yaml
poetry run python -m distributed_grid.cli cluster start -c config/my-cluster.yaml
```

### Validate the fix:
```bash
# Quick health check
poetry run python scripts/validate_ray_cluster.py -c config/my-cluster.yaml

# Monitor heartbeats for 2 minutes
poetry run python scripts/validate_ray_cluster.py -c config/my-cluster.yaml --monitor 120
```

## Impact
- More resilient to network delays
- Reduced false-positive node failures
- Better cluster stability
- Configurable timeouts for different environments

## Notes
- These settings are conservative and can be adjusted based on network conditions
- Monitor the dashboard after applying the fix to ensure stability
- Check logs if issues persist to fine-tune timeout values