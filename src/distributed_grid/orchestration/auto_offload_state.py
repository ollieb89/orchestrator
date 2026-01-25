"""State persistence for auto-offload feature."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

DEFAULT_STATE_FILE = Path.home() / ".distributed_grid" / "grid_offload_state.json"


@dataclass
class OffloadEvent:
    """An offload-related event."""
    timestamp: datetime
    event_type: str  # pressure_detected, offload_started, offload_completed, offload_failed
    node_id: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "node_id": self.node_id,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OffloadEvent":
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            event_type=data["event_type"],
            node_id=data["node_id"],
            details=data.get("details", {}),
        )


class AutoOffloadState:
    """Manages auto-offload state persistence."""

    MAX_EVENTS = 100

    def __init__(self, state_file: Optional[Path] = None):
        self.state_file = state_file or DEFAULT_STATE_FILE
        self.enabled: bool = False
        self.thresholds: Dict[str, int] = {"cpu": 80, "memory": 70, "gpu": 90}
        self.active_offloads: List[Dict[str, Any]] = []
        self.recent_events: List[OffloadEvent] = []

        # Load existing state if file exists
        if self.state_file.exists():
            self.load()

    def enable(self, cpu: int = 80, memory: int = 70, gpu: int = 90) -> None:
        """Enable auto-offload with specified thresholds."""
        self.enabled = True
        self.thresholds = {"cpu": cpu, "memory": memory, "gpu": gpu}
        self.save()
        logger.info("Auto-offload enabled", thresholds=self.thresholds)

    def disable(self) -> None:
        """Disable auto-offload."""
        self.enabled = False
        self.save()
        logger.info("Auto-offload disabled")

    def add_event(self, event: OffloadEvent) -> None:
        """Add an event to history, maintaining max size."""
        self.recent_events.append(event)
        if len(self.recent_events) > self.MAX_EVENTS:
            self.recent_events = self.recent_events[-self.MAX_EVENTS:]

    def add_active_offload(
        self,
        task_id: str,
        pid: int,
        target_node: str,
        command: str,
    ) -> None:
        """Track an active offload."""
        self.active_offloads.append({
            "task_id": task_id,
            "pid": pid,
            "target_node": target_node,
            "command": command,
            "started_at": datetime.now().isoformat(),
        })
        self.save()

    def remove_active_offload(self, task_id: str) -> None:
        """Remove a completed offload."""
        self.active_offloads = [
            o for o in self.active_offloads if o["task_id"] != task_id
        ]
        self.save()

    def save(self) -> None:
        """Persist state to file."""
        try:
            # Ensure parent directory exists
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "enabled": self.enabled,
                "thresholds": self.thresholds,
                "active_offloads": self.active_offloads,
                "recent_events": [e.to_dict() for e in self.recent_events],
            }
            self.state_file.write_text(json.dumps(data, indent=2))
        except OSError as e:
            logger.warning("Failed to save state file", path=str(self.state_file), error=str(e))

    def load(self) -> None:
        """Load state from file."""
        try:
            data = json.loads(self.state_file.read_text())
            self.enabled = data.get("enabled", False)
            self.thresholds = data.get("thresholds", {"cpu": 80, "memory": 70, "gpu": 90})
            self.active_offloads = data.get("active_offloads", [])
            self.recent_events = [
                OffloadEvent.from_dict(e) for e in data.get("recent_events", [])
            ]
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to load state file, using defaults", error=str(e))
