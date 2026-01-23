# Resource Boost Persistence Issue

## Problem Description

The Resource Boost Manager does not persist boosts between CLI command invocations. Each CLI command creates a new ResourceBoostManager instance with in-memory storage, causing all boosts to be lost when the command finishes.

## Root Cause Analysis

1. **In-memory storage only**: The ResourceBoostManager stores active boosts in `self._active_boosts`, a Python dictionary in memory
2. **No persistence layer**: Unlike the ResourceSharingManager which has file-based persistence, the boost manager lacks any persistence mechanism
3. **CLI creates new instances**: Each CLI command (`grid boost request`, `grid boost status`, `grid boost release`) creates a new ResourceBoostManager instance

## Evidence

```bash
# Request a boost
$ poetry run grid boost request gpu-master cpu 2.0 --priority high
✓ Resource boost requested successfully
Boost ID: 515744a0-b524-4565-af67-9be9d3367a2c

# Check status immediately after
$ poetry run grid boost status
Total Active Boosts: 0
No active boosts
```

The boost is created successfully but immediately lost when checking status.

## Impact

- **Boosts cannot be tracked**: Users cannot see active boosts after creation
- **Cannot release boosts**: The `grid boost release` command cannot find boosts created in previous commands
- **No workflow possible**: The intended workflow of request → use → release is broken
- **Misleading documentation**: The guide examples don't work as documented

## Comparison with Resource Sharing

The ResourceSharingManager has a working persistence implementation:

```python
# Has persistence layer
self._persistence = ResourceSharingPersistence()

# Saves to disk
await self._persistence.save_allocation(allocation)

# Loads from disk
allocations = await self._persistence.load_allocations()
```

The ResourceBoostManager lacks this entirely.

## Solution Options

### Option 1: Add File-based Persistence (Recommended)

Implement a similar persistence layer as ResourceSharingManager:

```python
class ResourceBoostPersistence:
    def __init__(self, storage_dir: Path = None):
        self.storage_dir = storage_dir or Path.home() / ".distributed_grid"
        self.boosts_file = self.storage_dir / "boosts.json"
    
    async def save_boost(self, boost: ResourceBoost):
        # Save to JSON file
    
    async def load_boosts(self) -> Dict[str, ResourceBoost]:
        # Load from JSON file
    
    async def delete_boost(self, boost_id: str):
        # Remove from JSON file
```

### Option 2: Use Ray Actors

Store boosts in a Ray detached actor for cluster-wide persistence. However, this had issues with the ResourceSharingManager (worker import problems).

### Option 3: Database Storage

Use SQLite for more robust persistence with querying capabilities.

## Implementation Plan for Option 1

1. Create `ResourceBoostPersistence` class in `src/distributed_grid/orchestration/resource_boost_persistence.py`
2. Update `ResourceBoostManager` to use persistence:
   - Add `_persistence` attribute
   - Save boosts on creation
   - Load boosts on initialization
   - Delete boosts on release
3. Update CLI to initialize with existing boosts
4. Add tests for persistence

## Code Changes Required

### New File: `resource_boost_persistence.py`
```python
"""Persistence layer for Resource Boost Manager."""

import json
import asyncio
from pathlib import Path
from datetime import datetime, UTC
from typing import Dict, List, Optional
import structlog

from .resource_boost_manager import ResourceBoost

logger = structlog.get_logger(__name__)

class ResourceBoostPersistence:
    """Handles persistence of resource boosts to disk."""
    
    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or Path.home() / ".distributed_grid"
        self.boosts_file = self.storage_dir / "boosts.json"
        self._boosts: Dict[str, ResourceBoost] = {}
    
    async def initialize(self):
        """Initialize persistence and load existing boosts."""
        await self._ensure_storage_dir()
        await self.load_boosts()
    
    async def save_boost(self, boost: ResourceBoost):
        """Save a boost to persistent storage."""
        self._boosts[boost.boost_id] = boost
        await self._save_to_disk()
    
    async def load_boosts(self) -> Dict[str, ResourceBoost]:
        """Load all boosts from persistent storage."""
        if not self.boosts_file.exists():
            return {}
        
        try:
            with open(self.boosts_file, 'r') as f:
                data = json.load(f)
            
            boosts = {}
            for boost_id, boost_data in data.items():
                # Convert dict back to ResourceBoost
                boosts[boost_id] = ResourceBoost(
                    boost_id=boost_data['boost_id'],
                    source_node=boost_data['source_node'],
                    target_node=boost_data['target_node'],
                    resource_type=ResourceType(boost_data['resource_type']),
                    amount=boost_data['amount'],
                    allocated_at=datetime.fromisoformat(boost_data['allocated_at']),
                    expires_at=datetime.fromisoformat(boost_data['expires_at']) if boost_data['expires_at'] else None,
                    ray_placement_group=boost_data.get('ray_placement_group'),
                    is_active=boost_data.get('is_active', True)
                )
            
            self._boosts = boosts
            logger.info(f"Loaded {len(boosts)} boosts from persistence")
            return boosts
            
        except Exception as e:
            logger.error(f"Failed to load boosts: {e}")
            return {}
    
    async def delete_boost(self, boost_id: str):
        """Delete a boost from persistent storage."""
        if boost_id in self._boosts:
            del self._boosts[boost_id]
            await self._save_to_disk()
    
    async def cleanup_expired(self):
        """Remove expired boosts from storage."""
        now = datetime.now(UTC)
        expired = [
            boost_id for boost_id, boost in self._boosts.items()
            if boost.expires_at and boost.expires_at < now
        ]
        
        for boost_id in expired:
            await self.delete_boost(boost_id)
        
        return len(expired)
    
    async def _ensure_storage_dir(self):
        """Ensure storage directory exists."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)
    
    async def _save_to_disk(self):
        """Save boosts to disk."""
        data = {}
        for boost_id, boost in self._boosts.items():
            data[boost_id] = {
                'boost_id': boost.boost_id,
                'source_node': boost.source_node,
                'target_node': boost.target_node,
                'resource_type': boost.resource_type.value,
                'amount': boost.amount,
                'allocated_at': boost.allocated_at.isoformat(),
                'expires_at': boost.expires_at.isoformat() if boost.expires_at else None,
                'ray_placement_group': boost.ray_placement_group,
                'is_active': boost.is_active
            }
        
        with open(self.boosts_file, 'w') as f:
            json.dump(data, f, indent=2)
```

### Changes to `resource_boost_manager.py`:
```python
# Add import
from .resource_boost_persistence import ResourceBoostPersistence

# In __init__:
self._persistence = ResourceBoostPersistence()

# In initialize():
await self._persistence.initialize()
self._active_boosts = await self._persistence.load_boosts()

# In request_boost():
await self._persistence.save_boost(boost)

# In release_boost():
await self._persistence.delete_boost(boost_id)
```

## Workaround

Until persistence is implemented, users can:

1. Use the Resource Sharing system instead, which has working persistence
2. Use boosts within a single Python script (not CLI commands)
3. Save boost IDs manually and use them programmatically

## Testing

Run the test script to see the issue in action:
```bash
poetry run python examples/resource_boost_test.py
```

## Status

- **Issue identified**: January 23, 2026
- **Impact**: High - breaks core functionality
- **Priority**: High - needs immediate fix
- **Complexity**: Medium - similar to existing ResourceSharingManager persistence
