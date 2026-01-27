# Grid Offloading + Ray Monitoring + CLI Design

Date: 2026-01-27

## Goals
- End-to-end offloading works on a 2-node Ray cluster.
- Auto-offload daemon runs and respects policy.
- Ray monitoring visible via TUI.
- CLI prompts for missing args (interactive), with consistent flags.

## Non-Goals
- Head-node offloading (explicitly disallowed).
- New web UI.
- Full CLI refactor beyond offloading/monitoring commands.

## Default Policy
Hybrid policy:
- Threshold-based triggers for CPU/memory/GPU.
- Queue-based trigger for pending jobs.
- Offload targets are worker nodes only.

## Architecture
- CLI is a thin adapter; all decisions flow through OffloadingService.
- OffloadingService owns policy, orchestration lifecycle, and monitoring.
- MonitorFacade wraps Ray + resource metrics into a stable snapshot schema.

## Components
- OffloadingService (new)
  - Public API: scan, execute, auto_enable/disable, status, history.
  - Initializes: MonitorFacade, PolicyEngine, OffloadingDetector, EnhancedOffloadingExecutor, ResourceSharingOrchestrator.
  - Enforces worker-only targets.

- PolicyEngine (new)
  - Inputs: ResourceSnapshot + QueueSnapshot + CLI overrides.
  - Output: PolicyDecision (allowed, reasons, effective thresholds).

- MonitorFacade (new)
  - Normalizes Ray cluster metrics + ResourceMetricsCollector.
  - Exposes get_snapshot() and stream_snapshots(interval).

- CLI layer (existing)
  - Prompts for missing args (TTY), errors in non-TTY.
  - Routes output to text/JSON/TUI.

- TUI Dashboard (existing)
  - Consumes MonitorFacade stream to display resources, queue depth, auto-offload state, and history.

- Persistence (existing)
  - AutoOffloadState used for daemon state tracking.

## Data Flow
1) `grid offload scan`
   - CLI validates args, prompts if missing.
   - OffloadingService reads snapshot, consults PolicyEngine.
   - OffloadingDetector returns candidates.
   - CLI renders table/JSON and stores history.

2) `grid offload execute`
   - CLI prompts for PID if missing.
   - OffloadingService enforces worker-only target.
   - EnhancedOffloadingExecutor executes; returns task id.

3) Auto-offload daemon
   - Loop: MonitorFacade -> PolicyEngine -> detect -> execute.
   - State persisted via AutoOffloadState.

4) TUI monitoring
   - `grid offload watch` subscribes to MonitorFacade stream.

## Error Handling
- Ray unavailable: monitoring degrades; execution returns RayUnavailable with guidance.
- No eligible targets: PolicyDenied/NoEligibleTarget; CLI shows node pressures.
- Invalid PID: ProcessNotFound.
- Resource conflicts: ResourceConflict with retry guidance.
- Auto-offload loop: errors logged, after N failures auto-disable and persist.

## Testing
- Unit:
  - PolicyEngine threshold/queue logic.
  - OffloadingService worker-only enforcement and validation.
  - MonitorFacade normalization + Ray fallback.
- Integration (skippable in CI):
  - Scan + execute on 2-node Ray cluster.
  - Auto-offload state persistence.
- CLI:
  - Prompting behavior (TTY vs non-TTY).
  - JSON output schema.
  - TUI snapshot streaming.

## Open Questions
- Exact schema for queue depth (Ray jobs vs internal queue).
- History retention limit for offloading events.

