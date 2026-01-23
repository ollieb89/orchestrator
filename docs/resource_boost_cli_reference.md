# Resource Boost CLI Reference

## Quick Commands

### Request Resources
```bash
# CPU boost
grid boost request <node> cpu <amount> [--priority LEVEL] [--duration SECONDS]

# GPU boost  
grid boost request <node> gpu <amount> [--priority LEVEL] [--duration SECONDS]

# Memory boost
grid boost request <node> memory <amount> [--priority LEVEL] [--duration SECONDS]
```

### Status & Release
```bash
# Check all boosts
grid boost status

# Check specific node
grid boost status --node <node>

# Release boost
grid boost release <boost-id>
```

## Examples

```bash
# Request 2 CPUs with high priority for 30 minutes
grid boost request gpu-master cpu 2.0 --priority high --duration 1800

# Request 1 GPU with critical priority
grid boost request gpu-master gpu 1 --priority critical

# Request 8GB memory from specific source
grid boost request gpu-master memory 8.0 --source gpu2

# Check status
grid boost status

# Release boost
grid boost release req_1234567890_gpu-master
```

## Priority Levels

- `low` - Lowest priority, pre-empted by others
- `normal` - Default priority level
- `high` - High priority, pre-empts normal/low
- `critical` - Highest priority, pre-empts all others

## Tips

1. Use `grid boost status` to see active boost IDs
2. Boosts auto-expire after duration (default: 1 hour)
3. Resources are automatically cleaned up on expiration
4. Use `--source` to specify preferred worker node
