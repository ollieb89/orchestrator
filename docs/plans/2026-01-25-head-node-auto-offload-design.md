# Head Node Auto-Offload Design

**Date:** 2026-01-25
**Status:** Approved
**Author:** Claude + User collaboration

## Overview

Enable intelligent automatic offloading from the head node (gpu-master) with simple CLI controls and real-time observability via a TUI dashboard.

## Goals

1. **Simple CLI** - Toggle-based commands to enable/disable auto-offload
2. **Head-only targeting** - Only monitor gpu-master; workers are destinations only
3. **Real-time observability** - Interactive TUI dashboard showing pressure, offloads, events

## Non-Goals

- Worker-to-worker offloading (out of scope)
- Systemd/production deployment automation (future enhancement)
- Webhook/external alerting (future enhancement)

## CLI Commands

```bash
# Enable automatic offloading from head node
grid offload auto --enable
grid offload auto --enable --threshold 70    # Custom memory threshold (%)
grid offload auto --enable --threshold cpu=80 memory=65 gpu=90

# Disable automatic offloading
grid offload auto --disable

# Check current auto-offload status
grid offload auto --status

# Launch interactive dashboard
grid offload watch
grid offload watch --interval 2    # Refresh every 2 seconds
```

### Command Behavior

**`--enable`:**
1. Validates cluster config exists
2. Sets `head_only_mode: true` in runtime config
3. Starts the daemon if not running (or reconfigures if running)
4. Confirms: "✓ Auto-offload enabled for gpu-master (memory: 70%, cpu: 80%)"

**`--disable`:**
1. Stops automatic offloading (daemon can keep running for other functions)
2. Confirms: "✓ Auto-offload disabled"

**`watch`:**
1. Connects to metrics collector (starts one if needed)
2. Launches Rich Live TUI
3. Shows real-time pressure, active offloads, recent events

## Head-Only Mode Implementation

### Configuration Addition

```python
class ResourceSharingConfig(BaseModel):
    # ... existing fields ...
    head_only_mode: bool = False  # When True, only monitor head node for offloading
```

### ResourceMetricsCollector Changes

```python
# In _monitoring_loop(), filter which nodes trigger pressure callbacks:
async def _monitoring_loop(self):
    while self._running:
        snapshots = await self._collect_all_metrics()

        for node_id, snapshot in snapshots.items():
            # HEAD-ONLY MODE: Skip pressure checks for workers
            if self._head_only_mode and node_id != self._head_node_id:
                continue

            # Existing pressure detection logic...
            if snapshot.memory_pressure > self._thresholds.memory_high:
                self._trigger_pressure_event(node_id, ResourceType.MEMORY, snapshot.memory_pressure)
```

### EnhancedOffloadingExecutor Changes

- Add validation: reject offload requests that would move TO gpu-master
- Workers remain valid targets only

### Runtime Toggle

- `grid offload auto --enable` sets `head_only_mode=True` via config file update
- Daemon picks up change without restart (config reload)

## TUI Dashboard

### Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  GRID OFFLOAD MONITOR                          Auto: ● ENABLED  │
├─────────────────────────────────────────────────────────────────┤
│  HEAD NODE: gpu-master                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ CPU    [████████████░░░░░░░░]  62%                      │    │
│  │ Memory [██████████████████░░]  89% ⚠ HIGH              │    │
│  │ GPU    [██████░░░░░░░░░░░░░░]  31%                      │    │
│  └─────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────┤
│  WORKERS (offload targets)                                      │
│  gpu1:  CPU 23%  Mem 45%  GPU 12%   ✓ Available                │
│  gpu2:  CPU 67%  Mem 52%  GPU 88%   ✓ Available                │
├─────────────────────────────────────────────────────────────────┤
│  ACTIVE OFFLOADS (2)                                            │
│  • PID 4521 → gpu1  python train.py      Running 5m 32s        │
│  • PID 4892 → gpu2  jupyter kernel       Running 2m 11s        │
├─────────────────────────────────────────────────────────────────┤
│  RECENT EVENTS                                                  │
│  14:32:01  Memory pressure detected (89%)                       │
│  14:32:03  Offloaded PID 4521 to gpu1                          │
│  14:35:22  Offloaded PID 4892 to gpu2                          │
└─────────────────────────────────────────────────────────────────┘
  [q] Quit  [p] Pause  [r] Refresh now  [o] Manual offload
```

### Implementation

- New file: `src/distributed_grid/tui/offload_dashboard.py`
- Uses `rich.live.Live` with `rich.table.Table` and `rich.panel.Panel`
- Pulls data from `ResourceMetricsCollector.get_all_latest_snapshots()`
- Subscribes to offload events from `EnhancedOffloadingExecutor`
- Refresh interval configurable (default 1s)

### Key Bindings

| Key | Action |
|-----|--------|
| `q` | Quit |
| `p` | Pause/resume auto-refresh |
| `r` | Force refresh |
| `o` | Open manual offload prompt |

## Configuration

### YAML Schema Addition

```yaml
execution:
  resource_sharing:
    # ... existing fields ...

    # New fields for head-only auto-offload
    auto_offload:
      enabled: false                    # Toggled by CLI
      head_only_mode: true              # Only offload FROM head node
      thresholds:
        cpu: 80
        memory: 70
        gpu: 90
      check_interval_seconds: 5         # How often to check pressure
      cooldown_seconds: 30              # Min time between offloads
```

### State Persistence

- Auto-offload state stored in `/tmp/grid_offload_state.json`
- Contains: enabled status, active offloads, event history
- Dashboard reads from here; daemon writes to here
- Survives dashboard restarts (daemon is source of truth)

### Daemon Communication

- Dashboard connects to daemon via Unix socket (`/tmp/grid_daemon.sock`)
- If daemon not running, dashboard starts metrics collection in read-only mode (no auto-offload, just monitoring)

## File Changes

| File | Change |
|------|--------|
| `cli.py` | Add `offload auto` and enhance `offload watch` |
| `config/models.py` | Add `AutoOffloadConfig` model |
| `resource_metrics.py` | Add `head_only_mode` filtering |
| `enhanced_offloading_executor.py` | Add target validation (no offload TO master) |
| `resource_sharing_orchestrator.py` | Wire up auto-offload config |
| `tui/offload_dashboard.py` | New file - Rich TUI dashboard |

## Implementation Order

1. Add `AutoOffloadConfig` to config models
2. Implement head-only mode in `ResourceMetricsCollector`
3. Add target validation in `EnhancedOffloadingExecutor`
4. Add `grid offload auto` CLI commands
5. Create TUI dashboard
6. Wire up `grid offload watch` to dashboard
7. Add state persistence and daemon communication
8. Write tests

## Testing Strategy

- Unit tests for head-only filtering logic
- Unit tests for CLI argument parsing
- Integration test: enable auto-offload, simulate pressure, verify offload triggered
- Manual testing of TUI dashboard responsiveness
