# Boost Manager Not Integrated with Scheduler

**Status:** pending  
**Priority:** p2  
**Issue ID:** boost-004  
**Tags:** code-review, architecture

## Problem Statement

The `IntelligentScheduler` doesn't check for active resource boosts when scheduling tasks. This means the scheduler doesn't know about boosted resources and can't use them when making scheduling decisions.

## Findings

**Location:** `src/distributed_grid/orchestration/intelligent_scheduler.py`

The scheduler:
- Doesn't have a reference to `ResourceBoostManager`
- Doesn't check for active boosts in `schedule_task()`
- Resource availability checks (`_meets_requirements`) only use snapshot data, not boosted resources

**Impact:**
- Scheduler may reject tasks that could run on boosted resources
- Boosted resources are not considered in scheduling decisions
- Inefficient resource utilization

## Proposed Solutions

### Solution 1: Pass Boost Manager to Scheduler

**Approach:** Add `ResourceBoostManager` as optional parameter to `IntelligentScheduler`.

**Pros:**
- Clean integration
- Scheduler can make informed decisions

**Cons:**
- Adds dependency
- Requires refactoring

**Effort:** Small  
**Risk:** Low

**Implementation:**
```python
class IntelligentScheduler:
    def __init__(
        self,
        ...,
        boost_manager: Optional[ResourceBoostManager] = None,
    ):
        self.boost_manager = boost_manager
    
    async def schedule_task(self, request: SchedulingRequest) -> SchedulingDecision:
        # Check for active boosts on eligible nodes
        if self.boost_manager:
            for node_id in eligible_nodes:
                boosts = await self.boost_manager.get_active_boosts(target_node=node_id)
                if boosts:
                    # Adjust available resources based on boosts
                    # ...
```

### Solution 2: Include Boosted Resources in Resource Snapshots

**Approach:** Modify `ResourceMetricsCollector` to include boosted resources in snapshots.

**Pros:**
- Transparent to scheduler
- Works with existing code

**Cons:**
- Requires modifying metrics collector
- Boosted resources may not be "real" (see issue boost-001)

**Effort:** Medium  
**Risk:** Medium

## Recommended Action

Implement **Solution 1** as it's cleaner and doesn't require modifying the metrics system. However, this should be done after fixing issue boost-001 to ensure boosted resources are actually available.

## Technical Details

**Affected Files:**
- `src/distributed_grid/orchestration/intelligent_scheduler.py`

**Related Components:**
- ResourceBoostManager
- IntelligentScheduler
- ResourceMetricsCollector

## Acceptance Criteria

- [ ] Scheduler can access boost manager
- [ ] Scheduler considers active boosts when scheduling
- [ ] Boosted resources are factored into scheduling decisions
- [ ] Tests verify scheduler behavior with active boosts

## Work Log

- 2026-01-24: Identified lack of integration between boost manager and scheduler

## Resources

- Related issue: `001-pending-p1-resource-boost-not-actually-adding-resources.md`
