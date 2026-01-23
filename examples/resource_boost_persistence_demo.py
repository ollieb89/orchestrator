#!/usr/bin/env python3
"""Demo script showing Resource Boost Manager persistence functionality.

This script demonstrates how resource boosts persist across different
process invocations, making the Resource Boost Manager functional for
real-world use.
"""

import asyncio
import json
import os
import time
from pathlib import Path

from distributed_grid.orchestration.resource_boost_persistence import (
    ResourceBoostPersistence,
)
from distributed_grid.monitoring.resource_metrics import ResourceType
from distributed_grid.orchestration.resource_boost_manager import (
    ResourceBoostManager,
    ResourceBoostRequest,
)
from distributed_grid.orchestration.resource_sharing_types import (
    AllocationPriority,
)


def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'='*60}")
    print(f" {title}")
    print('='*60)


def print_persistence_info(persistence: ResourceBoostPersistence):
    """Print information about the persistence file."""
    info = persistence.get_file_info()
    print(f"\n📁 Persistence file: {info['path']}")
    if info['exists']:
        print(f"   Size: {info['size_bytes']} bytes")
        print(f"   Modified: {info['modified']}")
    else:
        print("   Status: Does not exist")


async def demo_persistence():
    """Demonstrate the persistence functionality."""
    print_section("Resource Boost Manager Persistence Demo")
    
    # Show persistence file location
    persistence_dir = Path.home() / ".distributed_grid"
    persistence_file = persistence_dir / "resource_boosts.json"
    
    print(f"\n📍 Persistence directory: {persistence_dir}")
    print(f"📄 Boosts file: {persistence_file}")
    
    # Create a persistence instance
    persistence = ResourceBoostPersistence()
    print_persistence_info(persistence)
    
    print_section("\n1. Checking existing boosts")
    
    # Load any existing boosts
    existing_boosts = persistence.load_boosts()
    if existing_boosts:
        print(f"\nFound {len(existing_boosts)} existing boosts:")
        for boost in existing_boosts:
            print(f"  - {boost['boost_id'][:8]}...: "
                  f"{boost['amount']} {boost['resource_type']} "
                  f"from {boost['source_node']} to {boost['target_node']}")
    else:
        print("\nNo existing boosts found")
    
    print_section("\n2. Simulating CLI boost request")
    
    # Simulate what happens when a user requests a boost via CLI
    print("\nSimulating: grid boost request gpu-master cpu 2.0 --priority high")
    
    # Create a mock boost (normally done by ResourceBoostManager)
    from datetime import datetime, UTC, timedelta
    import uuid
    
    demo_boost = {
        "boost_id": str(uuid.uuid4()),
        "source_node": "gpu1",
        "target_node": "gpu-master",
        "resource_type": ResourceType.CPU,
        "amount": 2.0,
        "allocated_at": datetime.now(UTC),
        "expires_at": datetime.now(UTC) + timedelta(hours=1),
        "ray_placement_group": None,
        "is_active": True
    }
    
    # Save to persistence (what ResourceBoostManager does)
    persistence.save_boosts([demo_boost])
    print(f"\n✓ Created boost: {demo_boost['boost_id'][:8]}...")
    
    print_persistence_info(persistence)
    
    print_section("\n3. Simulating CLI status check")
    
    # Simulate checking status (new CLI invocation)
    print("\nSimulating: grid boost status")
    
    # Load boosts from persistence (what happens on new CLI invocation)
    loaded_boosts = persistence.load_boosts()
    
    print(f"\n📊 Active boosts: {len(loaded_boosts)}")
    if loaded_boosts:
        print("\nBoost details:")
        for boost in loaded_boosts:
            expires = boost['expires_at'].strftime("%H:%M:%S") if boost['expires_at'] else "Never"
            print(f"  ├─ ID: {boost['boost_id'][:8]}...")
            print(f"  ├─ Source: {boost['source_node']} → Target: {boost['target_node']}")
            print(f"  ├─ Resource: {boost['resource_type']} x{boost['amount']}")
            print(f"  └─ Expires: {expires}")
    
    print_section("\n4. Showing raw persistence file")
    
    # Show the actual JSON content
    if persistence_file.exists():
        print(f"\n📄 Content of {persistence_file}:")
        with open(persistence_file, 'r') as f:
            data = json.load(f)
            print(json.dumps(data, indent=2))
    
    print_section("\n5. Simulating boost release")
    
    # Simulate releasing a boost
    print(f"\nSimulating: grid boost release {demo_boost['boost_id'][:8]}...")
    
    # Clear all boosts (what happens when releasing)
    persistence.clear_boosts()
    print("\n✓ Boost released")
    
    print_persistence_info(persistence)
    
    print_section("\n6. Verifying persistence after release")
    
    # Check that boosts are gone
    final_boosts = persistence.load_boosts()
    print(f"\n📊 Active boosts after release: {len(final_boosts)}")
    
    print_section("\n✅ Demo Complete")
    
    print("\nKey takeaways:")
    print("  • Resource boosts are stored in ~/.distributed_grid/resource_boosts.json")
    print("  • Boosts persist across CLI invocations")
    print("  • Each CLI command loads existing boosts from disk")
    print("  • Changes are immediately saved back to disk")
    print("  • The system gracefully handles missing or corrupted files")
    
    print("\nTry it yourself with the CLI:")
    print("  1. poetry run grid boost request gpu-master cpu 2.0")
    print("  2. poetry run grid boost status")
    print("  3. poetry run grid boost release <boost-id>")


if __name__ == "__main__":
    asyncio.run(demo_persistence())
