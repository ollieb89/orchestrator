# Incorrect Placement Group Strategy for Resource Boosting

**Status:** pending  
**Priority:** p2  
**Issue ID:** boost-003  
**Tags:** code-review, bug

## Problem Statement

The resource boost manager uses `STRICT_SPREAD` strategy for placement groups, which tries to spread resources across multiple nodes. This is incorrect for resource boosting, which should target a specific node.

## Findings

**Location:** `src/distributed_grid/orchestration/resource_boost_manager.py:414`

```python
pg = placement_group(bundles_list, strategy="STRICT_SPREAD", name=pg_name)
```

**Issue:** `STRICT_SPREAD` strategy requires bundles to be placed on different nodes. For resource boosting, we want all resources on the target node (`boost.target_node`), so we should use `PACK` or `STRICT_PACK` strategy.

## Impact

- Resources may be placed on wrong nodes
- Boost may not be available on the intended target node
- Placement group creation may fail if there aren't enough nodes

## Proposed Solutions

### Solution 1: Use PACK Strategy (Recommended)

**Approach:** Change strategy to `PACK` to place all bundles on the same node.

**Pros:**
- Simple fix
- Ensures resources are on same node
- Works with single bundle

**Cons:**
- Still doesn't solve the core issue (placement groups reserve, not add)

**Effort:** Small  
**Risk:** Low

**Implementation:**
```python
pg = placement_group(bundles_list, strategy="PACK", name=pg_name)
```

### Solution 2: Use STRICT_PACK with Node Constraints

**Approach:** Use `STRICT_PACK` and add node-specific resource constraints.

**Pros:**
- More explicit about node targeting
- Can ensure placement on specific node

**Cons:**
- Requires node IP mapping
- More complex

**Effort:** Small  
**Risk:** Low

**Implementation:**
```python
# Get target node IP
target_node_config = next(
    n for n in self.cluster_config.nodes 
    if n.name == boost.target_node
)
target_ip = target_node_config.host

# Add node constraint
bundles_list = [{
    boost.resource_type.value.upper(): boost.amount,
    f"node:{target_ip}": 0.001
}]
pg = placement_group(bundles_list, strategy="STRICT_PACK", name=pg_name)
```

## Recommended Action

Implement **Solution 2** to ensure resources are placed on the correct node. This is a quick fix that should be done regardless of the larger architectural issues.

## Technical Details

**Affected Files:**
- `src/distributed_grid/orchestration/resource_boost_manager.py:414`

**Related Components:**
- Ray placement groups
- Cluster configuration

## Acceptance Criteria

- [ ] Placement group uses correct strategy (PACK or STRICT_PACK)
- [ ] Resources are placed on the target node specified in boost
- [ ] Tests verify correct node placement

## Work Log

- 2026-01-24: Identified incorrect placement group strategy
