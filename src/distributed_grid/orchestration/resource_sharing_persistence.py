"""Simple file-based persistence for resource sharing state."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ResourceSharingPersistence:
    """File-based persistence for resource sharing state."""
    
    def __init__(self, data_dir: Optional[str] = None):
        """Initialize persistence with a data directory."""
        if data_dir is None:
            data_dir = os.path.expanduser("~/.distributed_grid")
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.allocations_file = self.data_dir / "resource_allocations.json"
        self.shared_resources_file = self.data_dir / "shared_resources.json"
        
    def save_allocations(self, allocations: List[Dict[str, Any]]) -> None:
        """Save allocations to file."""
        try:
            with open(self.allocations_file, 'w') as f:
                json.dump({
                    "allocations": allocations,
                    "timestamp": datetime.utcnow().isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save allocations: {e}")
            
    def load_allocations(self) -> List[Dict[str, Any]]:
        """Load allocations from file."""
        try:
            if self.allocations_file.exists():
                with open(self.allocations_file, 'r') as f:
                    data = json.load(f)
                    return data.get("allocations", [])
        except Exception as e:
            logger.error(f"Failed to load allocations: {e}")
        return []
        
    def save_shared_resources(self, resources: Dict[str, Dict[str, float]]) -> None:
        """Save shared resources to file."""
        try:
            with open(self.shared_resources_file, 'w') as f:
                json.dump({
                    "resources": resources,
                    "timestamp": datetime.utcnow().isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save shared resources: {e}")
            
    def load_shared_resources(self) -> Dict[str, Dict[str, float]]:
        """Load shared resources from file."""
        try:
            if self.shared_resources_file.exists():
                with open(self.shared_resources_file, 'r') as f:
                    data = json.load(f)
                    return data.get("resources", {})
        except Exception as e:
            logger.error(f"Failed to load shared resources: {e}")
        return {}
        
    def clear_all(self) -> None:
        """Clear all persisted data."""
        try:
            if self.allocations_file.exists():
                self.allocations_file.unlink()
            if self.shared_resources_file.exists():
                self.shared_resources_file.unlink()
        except Exception as e:
            logger.error(f"Failed to clear persisted data: {e}")
