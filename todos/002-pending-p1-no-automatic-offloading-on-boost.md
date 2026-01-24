# No Automatic Process Offloading When Resource Boost is Active

**Status:** pending  
**Priority:** p1  
**Issue ID:** boost-002  
**Tags:** code-review, architecture, feature-gap

## Problem Statement

When a resource boost is active on the head node, processes are not automatically offloaded to workers. The offloading system doesn't check for active boosts and doesn't trigger automatic offloading when boosts are in effect.

## Findings

### 1. No Integration Between Boost Manager and Offloading Executor

**Location:** `src/distributed_grid/orchestration/enhanced_offloading_executor.py`

The `EnhancedOffloadingExecutor` class doesn't have any reference to `ResourceBoostManager` and doesn't check for active boosts when making offloading decisions.

**Evidence:**
- No import of `ResourceBoostManager` in `enhanced_offloading_executor.py`
- `_make_offloading_decision()` method doesn't check for active boosts
- No method to query boost status

### 2. Scheduler Doesn't Consider Active Boosts

**Location:** `src/distributed_grid/orchestration/intelligent_scheduler.py`

The `IntelligentScheduler` also doesn't check for active boosts when scheduling tasks.

**Evidence:**
- No reference to boost manager in scheduler
- `schedule_task()` doesn't consider boost status
- Resource availability checks don't account for boosted resources

### 3. No Automatic Trigger for Offloading

**Location:** `src/distributed_grid/orchestration/resource_sharing_orchestrator.py`

The resource sharing orchestrator has pressure-based offloading (`_handle_resource_pressure`), but it doesn't check if a boost is active before offloading.

**Evidence:**
- `_handle_resource_pressure()` triggers offloading based on pressure thresholds
- No check for active boosts before offloading
- Could offload processes even when head has boosted resources available

### 4. Offloading Decision Logic Doesn't Account for Boosts

**Location:** `src/distributed_grid/orchestration/enhanced_offloading_executor.py:251-328`

The `_make_offloading_decision()` method checks if master has resources:

```python
master_has_resources = (
    master_snapshot.cpu_available >= analysis.cpu_requirement and
    master_snapshot.memory_available >= analysis.memory_requirement_mb * 1024 * 1024 and
    master_snapshot.gpu_available >= analysis.gpu_requirement
)
```

**Issue:** This only checks current available resources from snapshots, not boosted resources that should be available.

## Impact

- **CRITICAL:** The intended workflow (boost head → offload processes) doesn't work automatically
- Users must manually trigger offloading even when boosts are active
- System doesn't take advantage of boosted resources on head node
- Processes may be offloaded unnecessarily when head has boosted capacity

## Proposed Solutions

### Solution 1: Integrate Boost Manager with Offloading Executor (Recommended)

**Approach:** Pass `ResourceBoostManager` to `EnhancedOffloadingExecutor` and check for active boosts before offloading.

**Pros:**
- Proper integration between systems
- Can make intelligent decisions based on boost status
- Can prioritize using boosted resources on head

**Cons:**
- Requires refactoring to pass boost manager
- Adds coupling between components

**Effort:** Medium  
**Risk:** Low

**Implementation:**
```python
class EnhancedOffloadingExecutor:
    def __init__(
        self,
        ...,
        boost_manager: Optional[ResourceBoostManager] = None,
    ):
        self.boost_manager = boost_manager
    
    async def _make_offloading_decision(...):
        # Check for active boosts on head
        if self.boost_manager:
            active_boosts = await self.boost_manager.get_active_boosts(target_node="gpu-master")
            if active_boosts:
                # Head has boosted resources, don't offload
                decision.target_node = "gpu-master"
                decision.use_boosted_resources = True
                return decision
```

### Solution 2: Add Boost-Aware Resource Checks

**Approach:** Modify resource snapshot calculations to include boosted resources.

**Pros:**
- Transparent to offloading logic
- Works with existing code paths

**Cons:**
- Requires modifying metrics collector
- Boosted resources may not be "real" (see issue boost-001)

**Effort:** Medium  
**Risk:** Medium (depends on fixing boost-001 first)

### Solution 3: Automatic Offloading Trigger on Boost Activation

**Approach:** When a boost is activated, automatically trigger offloading of existing processes.

**Pros:**
- Proactive approach
- Ensures processes are offloaded when boost starts

**Cons:**
- May offload processes unnecessarily
- Requires process detection and migration logic

**Effort:** Large  
**Risk:** Medium

**Implementation:**
```python
async def request_boost(self, request: ResourceBoostRequest) -> Optional[str]:
    # ... existing boost creation ...
    
    # After boost is created, trigger automatic offloading
    if boost.target_node == "gpu-master":
        await self._trigger_automatic_offloading(boost)
    
    return boost_id

async def _trigger_automatic_offloading(self, boost: ResourceBoost):
    """Trigger automatic offloading when boost is active."""
    # Get offloading detector
    # Scan for offloadable processes
    # Execute offloading for suitable processes
```

## Recommended Action

**Solution 1** is the best approach - integrate boost manager with offloading executor so it can make informed decisions. This should be combined with fixing issue boost-001 to ensure boosted resources are actually available.

## Technical Details

**Affected Files:**
- `src/distributed_grid/orchestration/enhanced_offloading_executor.py`
- `src/distributed_grid/orchestration/intelligent_scheduler.py`
- `src/distributed_grid/orchestration/resource_boost_manager.py`

**Related Components:**
- ResourceBoostManager
- EnhancedOffloadingExecutor
- IntelligentScheduler
- OffloadingDetector

## Acceptance Criteria

- [ ] Offloading executor checks for active boosts before offloading
- [ ] When boost is active on head, processes prefer using boosted resources
- [ ] Automatic offloading can be triggered when boost is activated (optional)
- [ ] Tests verify offloading behavior with active boosts

## Work Log

- 2026-01-24: Initial review identified lack of integration between boost manager and offloading system

## Resources

- Related issue: `001-pending-p1-resource-boost-not-actually-adding-resources.md`
