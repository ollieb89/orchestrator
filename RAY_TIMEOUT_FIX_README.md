# Quick Fix Guide: Ray RPC Timeout Errors

## TL;DR - What to Do Now

```bash
# 1. Stop the cluster
poetry run grid cluster stop -c config/my-cluster.yaml

# 2. Start it again (with fixes already applied)
poetry run grid cluster start -c config/my-cluster.yaml

# 3. Validate
poetry run python scripts/validate_ray_cluster.py -c config/my-cluster.yaml
```

## What Was Fixed

The cluster startup was failing because:
1. **Workers connected before GCS was ready** → Added 45s wait (was 30s)
2. **RPC timeout during handshake** → Added GRPC keepalive config
3. **All workers tried connecting at once** → Now sequential with 10s delays
4. **Ray startup too slow** → Increased SSH timeout to 120s (was 60s)

## Key Changes in Code

```python
# File: src/distributed_grid/cluster/__init__.py

# Change 1: More time for GCS startup
await asyncio.sleep(45)  # Line 125 (was 30)

# Change 2: Worker startup sequential with delays
for i, node in enumerate(worker_nodes):  # Line 254 (was concurrent)
    if i > 0:
        await asyncio.sleep(10)  # Space out connections

# Change 3: Longer SSH timeouts
timeout=120  # Lines 187, 307 (was 60)

# Change 4: GRPC keepalive + RPC settings  
RAY_grpc_keepalive_time_ms=30000
RAY_grpc_max_recv_message_length=536870912
# ... (see full doc for all settings)
```

## Expected Result

```
✓ Ray cluster is active!
✓ Worker gpu1 connected
✓ Worker gpu2 connected
Dashboard: http://localhost:8265
```

No more "RPC error: Deadline Exceeded"!

## If It Still Fails

1. Check network: `ping gpu1 && ping gpu2`
2. Check logs: `ssh gpu1 "tail -f /tmp/ray/*/logs/raylet.err"`
3. Increase timeouts further (see full documentation)

## Full Details

See: `.serena/memories/ray_timeout_rpc_deadline_fix_jan2026.md`
