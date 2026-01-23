"""File-based persistence for resource boost state.

This module provides simple JSON-based persistence for resource boosts,
allowing them to survive across CLI invocations and process restarts.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

from distributed_grid.monitoring.resource_metrics import ResourceType

logger = logging.getLogger(__name__)


class ResourceBoostPersistence:
    """File-based persistence for resource boost state."""
    
    def __init__(self, data_dir: Optional[str] = None):
        """Initialize persistence with a data directory.
        
        Args:
            data_dir: Directory to store persistence files.
                     Defaults to ~/.distributed_grid
        """
        if data_dir is None:
            data_dir = os.path.expanduser("~/.distributed_grid")
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.boosts_file = self.data_dir / "resource_boosts.json"
        
    def save_boosts(self, boosts: List[Dict[str, Any]]) -> None:
        """Save boosts to file.
        
        Args:
            boosts: List of boost dictionaries to save
        """
        try:
            # Convert datetime objects to ISO strings for JSON serialization
            serializable_boosts = []
            for boost in boosts:
                boost_copy = boost.copy()
                if 'allocated_at' in boost_copy:
                    if isinstance(boost_copy['allocated_at'], datetime):
                        boost_copy['allocated_at'] = boost_copy['allocated_at'].isoformat()
                if 'expires_at' in boost_copy and boost_copy['expires_at']:
                    if isinstance(boost_copy['expires_at'], datetime):
                        boost_copy['expires_at'] = boost_copy['expires_at'].isoformat()
                # Ensure resource_type is a string
                if 'resource_type' in boost_copy:
                    if hasattr(boost_copy['resource_type'], 'value'):
                        boost_copy['resource_type'] = boost_copy['resource_type'].value
                serializable_boosts.append(boost_copy)
            
            with open(self.boosts_file, 'w') as f:
                json.dump({
                    "boosts": serializable_boosts,
                    "timestamp": datetime.utcnow().isoformat()
                }, f, indent=2)
                
            logger.debug(f"Saved {len(boosts)} boosts to {self.boosts_file}")
            
        except Exception as e:
            logger.error(f"Failed to save boosts: {e}")
            
    def load_boosts(self) -> List[Dict[str, Any]]:
        """Load boosts from file.
        
        Returns:
            List of boost dictionaries
        """
        try:
            if self.boosts_file.exists():
                with open(self.boosts_file, 'r') as f:
                    data = json.load(f)
                    boosts = data.get("boosts", [])
                    
                    # Convert ISO strings back to datetime objects
                    for boost in boosts:
                        if 'allocated_at' in boost:
                            if isinstance(boost['allocated_at'], str):
                                boost['allocated_at'] = datetime.fromisoformat(boost['allocated_at'])
                        if 'expires_at' in boost and boost['expires_at']:
                            if isinstance(boost['expires_at'], str):
                                boost['expires_at'] = datetime.fromisoformat(boost['expires_at'])
                        # Convert resource_type back to enum
                        if 'resource_type' in boost:
                            if isinstance(boost['resource_type'], str):
                                try:
                                    boost['resource_type'] = ResourceType(boost['resource_type'])
                                except ValueError:
                                    logger.warning(f"Unknown resource type: {boost['resource_type']}")
                                    boost['resource_type'] = ResourceType.CPU  # Default fallback
                    
                    logger.debug(f"Loaded {len(boosts)} boosts from {self.boosts_file}")
                    return boosts
                    
        except Exception as e:
            logger.error(f"Failed to load boosts: {e}")
            
        return []
        
    def clear_boosts(self) -> None:
        """Clear all persisted boosts."""
        try:
            if self.boosts_file.exists():
                self.boosts_file.unlink()
                logger.debug("Cleared all persisted boosts")
        except Exception as e:
            logger.error(f"Failed to clear boosts: {e}")
            
    def get_file_info(self) -> Dict[str, Any]:
        """Get information about the persistence file.
        
        Returns:
            Dictionary with file information
        """
        try:
            if self.boosts_file.exists():
                stat = self.boosts_file.stat()
                return {
                    "exists": True,
                    "path": str(self.boosts_file),
                    "size_bytes": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                }
            else:
                return {
                    "exists": False,
                    "path": str(self.boosts_file)
                }
        except Exception as e:
            logger.error(f"Failed to get file info: {e}")
            return {
                "exists": False,
                "path": str(self.boosts_file),
                "error": str(e)
            }
