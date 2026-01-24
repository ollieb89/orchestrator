# Resource Boost Does Not Actually Add Resources to Head Node

**Status:** pending  
**Priority:** p1  
**Issue ID:** boost-001  
**Tags:** code-review, security, architecture, critical

## Problem Statement

The `ResourceBoostManager._add_ray_resources()` method does not actually add resources to the head node. Instead, it creates a Ray placement group that **reserves** resources from the existing pool, which means the head node doesn't get extra resources - it just reserves some of its own existing resources.

## Findings

### 1. Placement Groups Reserve, Not Add Resources

**Location:** `src/distributed_grid/orchestration/resource_boost_manager.py:385-430`

The current implementation uses Ray placement groups:

```python
pg = placement_group(bundles_list, strategy="STRICT_SPREAD", name=pg_name)
ray.get(pg.ready())
```

**Issue:** According to Ray documentation, placement groups **reserve** resources from the cluster's existing pool rather than adding new resources. The reserved resources can only be used by tasks/actors that explicitly use that placement group, and they don't expand the cluster's total capacity.

### 2. Wrong Placement Strategy

**Location:** `src/distributed_grid/orchestration/resource_boost_manager.py:414`

The code uses `STRICT_SPREAD` strategy:
```python
pg = placement_group(bundles_list, strategy="STRICT_SPREAD", name=pg_name)
```

**Issue:** `STRICT_SPREAD` tries to spread bundles across multiple nodes, which is the opposite of what we want. We want to add resources to a specific target node (`boost.target_node`), not spread them.

### 3. No Node Targeting

**Location:** `src/distributed_grid/orchestration/resource_boost_manager.py:405-418`

The placement group creation doesn't specify which node to place resources on. It relies on Ray's automatic placement, which may not place resources on the intended target node.

### 4. Resources Not Actually Available to Head Node

The boosted resources are tracked in `self._boosted_resources` but this is just internal bookkeeping. Ray doesn't know about these as actual available resources on the target node, so tasks scheduled on the head node won't see or use these "boosted" resources.

## Evidence

1. **Ray Documentation Confirms:** Placement groups reserve resources, they don't add new ones
2. **Code Analysis:** The placement group is created without node-specific targeting
3. **No Resource Registration:** There's no code that actually registers these resources with Ray as available on the target node

## Impact

- **CRITICAL:** The entire resource boost feature doesn't work as intended
- Users requesting boosts expect the head node to get extra resources, but it doesn't
- This is a fundamental architectural flaw that makes the feature non-functional

## Proposed Solutions

### Solution 1: Use Ray Custom Resources (Recommended)

**Approach:** Use Ray's custom resource mechanism to actually add resources to the target node.

**Pros:**
- Actually adds resources that Ray can see and use
- Resources become available to all tasks on that node
- Proper integration with Ray's scheduler

**Cons:**
- Requires access to Ray's internal APIs or cluster configuration
- May need to coordinate with Ray cluster management

**Effort:** Large  
**Risk:** Medium (requires understanding Ray internals)

**Implementation:**
```python
# Use Ray's set_resource API (if available) or custom resources
# This would require modifying Ray cluster state or using Ray's resource API
```

### Solution 2: Use Remote Execution on Source Node

**Approach:** Instead of "adding" resources to the head, execute tasks on the source worker node that provided the boost.

**Pros:**
- Works with existing Ray infrastructure
- Resources are actually available (on the worker)
- Simpler implementation

**Cons:**
- Doesn't actually boost the head node
- Changes the semantics of "boost"

**Effort:** Medium  
**Risk:** Low

### Solution 3: Use Ray Placement Groups with Node Affinity

**Approach:** Create placement groups with node-specific constraints to ensure resources are reserved on the target node.

**Pros:**
- Uses existing Ray APIs
- Can target specific nodes

**Cons:**
- Still only reserves, doesn't add resources
- Resources only available to tasks using that placement group

**Effort:** Small  
**Risk:** Low (but doesn't solve the core issue)

**Implementation:**
```python
# Use node-specific resource constraints
bundles_list = [{
    boost.resource_type.value.upper(): boost.amount,
    f"node:{target_node_ip}": 0.001  # Pin to specific node
}]
pg = placement_group(bundles_list, strategy="PACK", name=pg_name)
```

## Recommended Action

**Solution 1** is the correct approach but requires significant work. **Solution 3** is a quick fix that at least ensures resources are reserved on the correct node, but doesn't solve the fundamental issue.

**Immediate Fix:** Implement Solution 3 to at least ensure placement groups target the correct node.

**Long-term Fix:** Research and implement Solution 1 to actually add resources to nodes.

## Technical Details

**Affected Files:**
- `src/distributed_grid/orchestration/resource_boost_manager.py` (lines 385-430)

**Related Components:**
- Ray placement groups
- Ray resource management
- Resource sharing manager

## Acceptance Criteria

- [ ] Resources are actually available to tasks on the head node (not just reserved)
- [ ] Placement groups target the correct node (boost.target_node)
- [ ] Ray scheduler can see and use the boosted resources
- [ ] Tests verify that boosted resources are actually available

## Work Log

- 2026-01-24: Initial review identified that placement groups don't add resources, only reserve them

## Resources

- [Ray Placement Groups Documentation](https://docs.ray.io/en/latest/ray-core/scheduling/placement-group.html)
- [Ray Resources Documentation](https://docs.ray.io/en/latest/ray-core/scheduling/resources.html)
