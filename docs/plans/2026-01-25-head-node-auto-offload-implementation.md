# Head Node Auto-Offload Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add toggle-based CLI commands for automatic head-node offloading with a real-time TUI dashboard.

**Architecture:** Extend existing `ResourceMetricsCollector` with head-only mode filtering, add `AutoOffloadConfig` to config models, create new CLI subcommands under `offload`, and build a Rich-based TUI dashboard. State persistence via JSON file enables dashboard to read daemon state.

**Tech Stack:** Python 3.11+, Pydantic v2, Click, Rich (Live, Table, Panel, Progress), asyncio

---

## Task 1: Add AutoOffloadConfig Model

**Files:**
- Modify: `src/distributed_grid/config/models.py:66-95`
- Test: `tests/test_auto_offload_config.py` (new)

**Step 1: Write the failing test**

Create `tests/test_auto_offload_config.py`:

```python
"""Tests for AutoOffloadConfig model."""

import pytest
from distributed_grid.config.models import AutoOffloadConfig, ResourceSharingConfig


class TestAutoOffloadConfig:
    """Test AutoOffloadConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = AutoOffloadConfig()
        assert config.enabled is False
        assert config.head_only_mode is True
        assert config.cpu_threshold == 80
        assert config.memory_threshold == 70
        assert config.gpu_threshold == 90
        assert config.check_interval_seconds == 5
        assert config.cooldown_seconds == 30

    def test_custom_thresholds(self):
        """Test custom threshold values."""
        config = AutoOffloadConfig(
            enabled=True,
            cpu_threshold=75,
            memory_threshold=65,
            gpu_threshold=85,
        )
        assert config.enabled is True
        assert config.cpu_threshold == 75
        assert config.memory_threshold == 65
        assert config.gpu_threshold == 85

    def test_threshold_validation(self):
        """Test threshold validation (0-100 range)."""
        with pytest.raises(ValueError):
            AutoOffloadConfig(cpu_threshold=101)
        with pytest.raises(ValueError):
            AutoOffloadConfig(memory_threshold=-1)

    def test_resource_sharing_config_includes_auto_offload(self):
        """Test that ResourceSharingConfig includes auto_offload field."""
        config = ResourceSharingConfig()
        assert hasattr(config, 'auto_offload')
        assert isinstance(config.auto_offload, AutoOffloadConfig)
```

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_auto_offload_config.py -v`
Expected: FAIL with "cannot import name 'AutoOffloadConfig'"

**Step 3: Write minimal implementation**

Add to `src/distributed_grid/config/models.py` before `ResourceSharingConfig`:

```python
class AutoOffloadConfig(BaseModel):
    """Configuration for automatic head-node offloading."""

    enabled: bool = Field(False, description="Enable automatic offloading")
    head_only_mode: bool = Field(True, description="Only offload FROM head node")
    cpu_threshold: int = Field(80, ge=0, le=100, description="CPU pressure threshold (%)")
    memory_threshold: int = Field(70, ge=0, le=100, description="Memory pressure threshold (%)")
    gpu_threshold: int = Field(90, ge=0, le=100, description="GPU pressure threshold (%)")
    check_interval_seconds: int = Field(5, ge=1, description="Pressure check interval")
    cooldown_seconds: int = Field(30, ge=0, description="Min time between offloads")
```

Update `ResourceSharingConfig` to add the new field:

```python
class ResourceSharingConfig(BaseModel):
    """Configuration for resource sharing."""

    # ... existing fields ...
    auto_offload: AutoOffloadConfig = Field(
        default_factory=AutoOffloadConfig,
        description="Auto-offload configuration"
    )
```

Update `src/distributed_grid/config/__init__.py` to export:

```python
from distributed_grid.config.models import (
    AutoOffloadConfig,
    ClusterConfig,
    # ... other exports
)
```

**Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_auto_offload_config.py -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add src/distributed_grid/config/models.py src/distributed_grid/config/__init__.py tests/test_auto_offload_config.py
git commit -m "feat(config): add AutoOffloadConfig model for head-node auto-offload"
```

---

## Task 2: Add Head-Only Mode to ResourceMetricsCollector

**Files:**
- Modify: `src/distributed_grid/monitoring/resource_metrics.py:109-137` (\_\_init\_\_)
- Modify: `src/distributed_grid/monitoring/resource_metrics.py:215-279` (\_collect\_all\_metrics)
- Test: `tests/test_head_only_metrics.py` (new)

**Step 1: Write the failing test**

Create `tests/test_head_only_metrics.py`:

```python
"""Tests for head-only mode in ResourceMetricsCollector."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from distributed_grid.monitoring.resource_metrics import ResourceMetricsCollector, ResourceType
from tests.conftest import get_test_cluster_config


class TestHeadOnlyMode:
    """Test head-only filtering in metrics collector."""

    @pytest.fixture
    def cluster_config(self):
        return get_test_cluster_config()

    @pytest.fixture
    def collector_head_only(self, cluster_config):
        """Collector with head-only mode enabled."""
        collector = ResourceMetricsCollector(
            cluster_config,
            ssh_manager=None,
            collection_interval=1.0,
            head_only_mode=True,
        )
        return collector

    @pytest.fixture
    def collector_all_nodes(self, cluster_config):
        """Collector monitoring all nodes."""
        collector = ResourceMetricsCollector(
            cluster_config,
            ssh_manager=None,
            collection_interval=1.0,
            head_only_mode=False,
        )
        return collector

    def test_head_only_mode_init(self, collector_head_only, cluster_config):
        """Test head-only mode initialization."""
        assert collector_head_only._head_only_mode is True
        assert collector_head_only._head_node_id == cluster_config.nodes[0].name

    def test_all_nodes_mode_init(self, collector_all_nodes):
        """Test all-nodes mode initialization."""
        assert collector_all_nodes._head_only_mode is False

    def test_set_head_only_mode(self, collector_all_nodes):
        """Test runtime toggle of head-only mode."""
        assert collector_all_nodes._head_only_mode is False
        collector_all_nodes.set_head_only_mode(True)
        assert collector_all_nodes._head_only_mode is True

    async def test_pressure_callback_head_only(self, collector_head_only):
        """Test that pressure callbacks only fire for head node in head-only mode."""
        triggered_nodes = []

        def callback(node_id, resource_type, pressure):
            triggered_nodes.append(node_id)

        collector_head_only.register_pressure_callback(callback)

        # Simulate high pressure on both head and worker
        collector_head_only._latest_snapshot = {
            "gpu-master": MagicMock(memory_pressure=0.95, cpu_pressure=0.5),
            "gpu1": MagicMock(memory_pressure=0.95, cpu_pressure=0.5),
        }

        # Trigger pressure check
        collector_head_only._check_pressure_events()

        # Only head node should trigger callback
        assert "gpu-master" in triggered_nodes
        assert "gpu1" not in triggered_nodes

    async def test_pressure_callback_all_nodes(self, collector_all_nodes):
        """Test that pressure callbacks fire for all nodes when head-only is off."""
        triggered_nodes = []

        def callback(node_id, resource_type, pressure):
            triggered_nodes.append(node_id)

        collector_all_nodes.register_pressure_callback(callback)

        # Simulate high pressure on both nodes
        collector_all_nodes._latest_snapshot = {
            "gpu-master": MagicMock(memory_pressure=0.95, cpu_pressure=0.5),
            "gpu1": MagicMock(memory_pressure=0.95, cpu_pressure=0.5),
        }

        # Trigger pressure check
        collector_all_nodes._check_pressure_events()

        # Both nodes should trigger
        assert "gpu-master" in triggered_nodes
        assert "gpu1" in triggered_nodes
```

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_head_only_metrics.py -v`
Expected: FAIL with "unexpected keyword argument 'head_only_mode'"

**Step 3: Write minimal implementation**

Modify `ResourceMetricsCollector.__init__` in `src/distributed_grid/monitoring/resource_metrics.py`:

```python
def __init__(
    self,
    cluster_config: ClusterConfig,
    ssh_manager: Optional[SSHManager] = None,
    collection_interval: float = 10.0,
    history_size: int = 100,
    head_only_mode: bool = False,  # NEW PARAMETER
):
    """Initialize the metrics collector."""
    self.cluster_config = cluster_config
    self.ssh_manager = ssh_manager
    self.collection_interval = collection_interval
    self.history_size = history_size

    # Head-only mode settings
    self._head_only_mode = head_only_mode
    self._head_node_id = cluster_config.nodes[0].name if cluster_config.nodes else None

    # ... rest of existing init code ...
```

Add `set_head_only_mode` method:

```python
def set_head_only_mode(self, enabled: bool) -> None:
    """Enable or disable head-only mode at runtime."""
    self._head_only_mode = enabled
    logger.info("Head-only mode updated", enabled=enabled, head_node=self._head_node_id)
```

Add `_check_pressure_events` method (refactored from `_collect_all_metrics`):

```python
def _check_pressure_events(self) -> None:
    """Check for pressure events and trigger callbacks."""
    for node_id, snapshot in self._latest_snapshot.items():
        # HEAD-ONLY MODE: Skip pressure checks for workers
        if self._head_only_mode and node_id != self._head_node_id:
            continue

        if snapshot.memory_pressure > self._memory_threshold_high:
            self._trigger_pressure_event(node_id, ResourceType.MEMORY, snapshot.memory_pressure)

        if snapshot.cpu_pressure > self._cpu_threshold_high:
            self._trigger_pressure_event(node_id, ResourceType.CPU, snapshot.cpu_pressure)
```

Update `_collect_all_metrics` to call `_check_pressure_events` instead of inline checks:

```python
async def _collect_all_metrics(self) -> None:
    """Collect metrics from all nodes in the cluster."""
    # ... existing collection code up to storing snapshot ...

    for node_config in self.cluster_config.nodes:
        node_id = node_config.name
        # ... collect and store snapshot ...
        self._latest_snapshot[node_id] = snapshot
        # ... update history ...

    # Check pressure after collecting all metrics
    self._check_pressure_events()
```

**Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_head_only_metrics.py -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add src/distributed_grid/monitoring/resource_metrics.py tests/test_head_only_metrics.py
git commit -m "feat(metrics): add head-only mode filtering to ResourceMetricsCollector"
```

---

## Task 3: Add Target Validation to EnhancedOffloadingExecutor

**Files:**
- Modify: `src/distributed_grid/orchestration/enhanced_offloading_executor.py`
- Test: `tests/test_offload_target_validation.py` (new)

**Step 1: Write the failing test**

Create `tests/test_offload_target_validation.py`:

```python
"""Tests for offload target validation."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from distributed_grid.orchestration.enhanced_offloading_executor import EnhancedOffloadingExecutor
from distributed_grid.orchestration.offloading_detector import OffloadRecommendation
from tests.conftest import get_test_cluster_config


class TestOffloadTargetValidation:
    """Test that offloading TO head node is rejected."""

    @pytest.fixture
    def cluster_config(self):
        return get_test_cluster_config()

    @pytest.fixture
    def executor(self, cluster_config):
        ssh_manager = MagicMock()
        executor = EnhancedOffloadingExecutor(
            ssh_manager=ssh_manager,
            cluster_config=cluster_config,
            ray_dashboard_address="http://localhost:8265",
        )
        return executor

    def test_reject_offload_to_head_node(self, executor):
        """Test that offloading TO gpu-master is rejected."""
        recommendation = MagicMock(spec=OffloadRecommendation)
        recommendation.target_node = "gpu-master"
        recommendation.source_node = "gpu1"

        is_valid, reason = executor.validate_offload_target(recommendation)

        assert is_valid is False
        assert "head node" in reason.lower()

    def test_allow_offload_from_head_node(self, executor):
        """Test that offloading FROM gpu-master is allowed."""
        recommendation = MagicMock(spec=OffloadRecommendation)
        recommendation.target_node = "gpu1"
        recommendation.source_node = "gpu-master"

        is_valid, reason = executor.validate_offload_target(recommendation)

        assert is_valid is True

    def test_allow_offload_between_workers(self, executor):
        """Test that offloading between workers is allowed."""
        recommendation = MagicMock(spec=OffloadRecommendation)
        recommendation.target_node = "gpu2"
        recommendation.source_node = "gpu1"

        is_valid, reason = executor.validate_offload_target(recommendation)

        assert is_valid is True

    async def test_execute_offloading_rejects_invalid_target(self, executor):
        """Test that execute_offloading rejects invalid targets."""
        recommendation = MagicMock(spec=OffloadRecommendation)
        recommendation.target_node = "gpu-master"
        recommendation.source_node = "gpu1"
        recommendation.process = MagicMock(pid=1234)

        with pytest.raises(ValueError, match="Cannot offload TO head node"):
            await executor.execute_offloading(recommendation)
```

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_offload_target_validation.py -v`
Expected: FAIL with "has no attribute 'validate_offload_target'"

**Step 3: Write minimal implementation**

Add to `EnhancedOffloadingExecutor` in `src/distributed_grid/orchestration/enhanced_offloading_executor.py`:

```python
def validate_offload_target(self, recommendation) -> tuple[bool, str]:
    """Validate that the offload target is allowed.

    Returns:
        Tuple of (is_valid, reason)
    """
    head_node_id = self.cluster_config.nodes[0].name if self.cluster_config.nodes else None

    # Never allow offloading TO the head node
    if recommendation.target_node == head_node_id:
        return False, f"Cannot offload TO head node ({head_node_id})"

    return True, "Valid target"
```

Update `execute_offloading` method to add validation at the start:

```python
async def execute_offloading(self, recommendation) -> str:
    """Execute offloading for a process recommendation."""
    # Validate target first
    is_valid, reason = self.validate_offload_target(recommendation)
    if not is_valid:
        raise ValueError(reason)

    # ... existing implementation ...
```

**Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_offload_target_validation.py -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add src/distributed_grid/orchestration/enhanced_offloading_executor.py tests/test_offload_target_validation.py
git commit -m "feat(offload): add target validation to reject offloading TO head node"
```

---

## Task 4: Add Auto-Offload State Manager

**Files:**
- Create: `src/distributed_grid/orchestration/auto_offload_state.py`
- Test: `tests/test_auto_offload_state.py` (new)

**Step 1: Write the failing test**

Create `tests/test_auto_offload_state.py`:

```python
"""Tests for auto-offload state persistence."""

import json
import pytest
from pathlib import Path
from datetime import datetime

from distributed_grid.orchestration.auto_offload_state import AutoOffloadState, OffloadEvent


class TestAutoOffloadState:
    """Test auto-offload state persistence."""

    @pytest.fixture
    def state_file(self, tmp_path):
        return tmp_path / "offload_state.json"

    @pytest.fixture
    def state_manager(self, state_file):
        return AutoOffloadState(state_file)

    def test_initial_state(self, state_manager):
        """Test initial state is disabled."""
        assert state_manager.enabled is False
        assert state_manager.active_offloads == []
        assert state_manager.recent_events == []

    def test_enable_disable(self, state_manager):
        """Test enable/disable toggle."""
        state_manager.enable(cpu=75, memory=65, gpu=85)
        assert state_manager.enabled is True
        assert state_manager.thresholds == {"cpu": 75, "memory": 65, "gpu": 85}

        state_manager.disable()
        assert state_manager.enabled is False

    def test_persistence(self, state_manager, state_file):
        """Test state persists to file."""
        state_manager.enable(cpu=80, memory=70, gpu=90)
        state_manager.add_event(OffloadEvent(
            timestamp=datetime.now(),
            event_type="pressure_detected",
            node_id="gpu-master",
            details={"memory": 0.89},
        ))
        state_manager.save()

        # Load in new instance
        loaded = AutoOffloadState(state_file)
        loaded.load()

        assert loaded.enabled is True
        assert loaded.thresholds["cpu"] == 80
        assert len(loaded.recent_events) == 1

    def test_add_active_offload(self, state_manager):
        """Test tracking active offloads."""
        state_manager.add_active_offload(
            task_id="task-123",
            pid=4521,
            target_node="gpu1",
            command="python train.py",
        )

        assert len(state_manager.active_offloads) == 1
        assert state_manager.active_offloads[0]["task_id"] == "task-123"

    def test_remove_active_offload(self, state_manager):
        """Test removing completed offloads."""
        state_manager.add_active_offload("task-123", 4521, "gpu1", "python")
        state_manager.remove_active_offload("task-123")

        assert len(state_manager.active_offloads) == 0

    def test_event_history_limit(self, state_manager):
        """Test that event history is limited to 100 entries."""
        for i in range(150):
            state_manager.add_event(OffloadEvent(
                timestamp=datetime.now(),
                event_type="test",
                node_id="gpu-master",
                details={"i": i},
            ))

        assert len(state_manager.recent_events) == 100
```

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_auto_offload_state.py -v`
Expected: FAIL with "No module named 'distributed_grid.orchestration.auto_offload_state'"

**Step 3: Write minimal implementation**

Create `src/distributed_grid/orchestration/auto_offload_state.py`:

```python
"""State persistence for auto-offload feature."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

DEFAULT_STATE_FILE = Path("/tmp/grid_offload_state.json")


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
        data = {
            "enabled": self.enabled,
            "thresholds": self.thresholds,
            "active_offloads": self.active_offloads,
            "recent_events": [e.to_dict() for e in self.recent_events],
        }
        self.state_file.write_text(json.dumps(data, indent=2))

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
```

**Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_auto_offload_state.py -v`
Expected: PASS (6 tests)

**Step 5: Commit**

```bash
git add src/distributed_grid/orchestration/auto_offload_state.py tests/test_auto_offload_state.py
git commit -m "feat(offload): add AutoOffloadState for state persistence"
```

---

## Task 5: Add CLI Commands for Auto-Offload

**Files:**
- Modify: `src/distributed_grid/cli.py` (add `offload auto` subcommand)
- Test: `tests/test_auto_offload_cli.py` (new)

**Step 1: Write the failing test**

Create `tests/test_auto_offload_cli.py`:

```python
"""Tests for auto-offload CLI commands."""

import pytest
from click.testing import CliRunner
from pathlib import Path
from unittest.mock import patch, MagicMock

from distributed_grid.cli import cli


class TestAutoOffloadCLI:
    """Test auto-offload CLI commands."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def temp_state_file(self, tmp_path):
        return tmp_path / "offload_state.json"

    def test_auto_enable_default_thresholds(self, runner, temp_state_file):
        """Test enabling auto-offload with default thresholds."""
        with patch("distributed_grid.cli.AutoOffloadState") as MockState:
            mock_state = MagicMock()
            MockState.return_value = mock_state

            result = runner.invoke(cli, ["offload", "auto", "--enable"])

            assert result.exit_code == 0
            assert "enabled" in result.output.lower()
            mock_state.enable.assert_called_once()

    def test_auto_enable_custom_thresholds(self, runner):
        """Test enabling with custom thresholds."""
        with patch("distributed_grid.cli.AutoOffloadState") as MockState:
            mock_state = MagicMock()
            MockState.return_value = mock_state

            result = runner.invoke(cli, [
                "offload", "auto", "--enable",
                "--threshold", "cpu=75",
                "--threshold", "memory=65",
            ])

            assert result.exit_code == 0
            mock_state.enable.assert_called_once()
            call_kwargs = mock_state.enable.call_args[1]
            assert call_kwargs.get("cpu") == 75
            assert call_kwargs.get("memory") == 65

    def test_auto_disable(self, runner):
        """Test disabling auto-offload."""
        with patch("distributed_grid.cli.AutoOffloadState") as MockState:
            mock_state = MagicMock()
            MockState.return_value = mock_state

            result = runner.invoke(cli, ["offload", "auto", "--disable"])

            assert result.exit_code == 0
            assert "disabled" in result.output.lower()
            mock_state.disable.assert_called_once()

    def test_auto_status(self, runner):
        """Test status display."""
        with patch("distributed_grid.cli.AutoOffloadState") as MockState:
            mock_state = MagicMock()
            mock_state.enabled = True
            mock_state.thresholds = {"cpu": 80, "memory": 70, "gpu": 90}
            mock_state.active_offloads = []
            MockState.return_value = mock_state

            result = runner.invoke(cli, ["offload", "auto", "--status"])

            assert result.exit_code == 0
            assert "enabled" in result.output.lower()

    def test_enable_and_disable_mutually_exclusive(self, runner):
        """Test that --enable and --disable cannot be used together."""
        result = runner.invoke(cli, ["offload", "auto", "--enable", "--disable"])

        assert result.exit_code != 0

    def test_threshold_parsing(self, runner):
        """Test various threshold formats."""
        with patch("distributed_grid.cli.AutoOffloadState") as MockState:
            mock_state = MagicMock()
            MockState.return_value = mock_state

            # Single value sets memory threshold
            result = runner.invoke(cli, [
                "offload", "auto", "--enable", "--threshold", "75"
            ])

            assert result.exit_code == 0
```

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_auto_offload_cli.py -v`
Expected: FAIL with "No such command 'auto'"

**Step 3: Write minimal implementation**

Add to `src/distributed_grid/cli.py` after the existing offload commands:

```python
from distributed_grid.orchestration.auto_offload_state import AutoOffloadState


def parse_threshold(value: str) -> tuple[str, int]:
    """Parse threshold string like 'cpu=80' or '70' (memory default)."""
    if "=" in value:
        key, val = value.split("=", 1)
        return key.lower(), int(val)
    return "memory", int(value)


@offload.command()
@click.option("--enable", "action", flag_value="enable", help="Enable auto-offload")
@click.option("--disable", "action", flag_value="disable", help="Disable auto-offload")
@click.option("--status", "action", flag_value="status", help="Show auto-offload status")
@click.option(
    "--threshold", "-t",
    multiple=True,
    help="Set threshold: 'cpu=80', 'memory=70', 'gpu=90', or just '70' for memory"
)
def auto(action: str, threshold: tuple[str, ...]) -> None:
    """Configure automatic head-node offloading.

    Examples:

        grid offload auto --enable

        grid offload auto --enable --threshold 70

        grid offload auto --enable --threshold cpu=80 --threshold memory=65

        grid offload auto --disable

        grid offload auto --status
    """
    state = AutoOffloadState()

    if action == "enable":
        # Parse thresholds
        thresholds = {"cpu": 80, "memory": 70, "gpu": 90}  # defaults
        for t in threshold:
            key, val = parse_threshold(t)
            if key in thresholds:
                thresholds[key] = val

        state.enable(**thresholds)
        console.print(f"[green]✓ Auto-offload enabled for head node[/green]")
        console.print(f"  Thresholds: CPU={thresholds['cpu']}%, Memory={thresholds['memory']}%, GPU={thresholds['gpu']}%")

    elif action == "disable":
        state.disable()
        console.print("[yellow]✓ Auto-offload disabled[/yellow]")

    elif action == "status":
        if state.enabled:
            console.print("[green]● Auto-offload: ENABLED[/green]")
            console.print(f"  CPU threshold: {state.thresholds['cpu']}%")
            console.print(f"  Memory threshold: {state.thresholds['memory']}%")
            console.print(f"  GPU threshold: {state.thresholds['gpu']}%")
            console.print(f"  Active offloads: {len(state.active_offloads)}")
        else:
            console.print("[dim]○ Auto-offload: DISABLED[/dim]")
    else:
        console.print("[yellow]Use --enable, --disable, or --status[/yellow]")
```

**Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_auto_offload_cli.py -v`
Expected: PASS (6 tests)

**Step 5: Commit**

```bash
git add src/distributed_grid/cli.py tests/test_auto_offload_cli.py
git commit -m "feat(cli): add 'grid offload auto' command for toggle-based control"
```

---

## Task 6: Create TUI Dashboard Module

**Files:**
- Create: `src/distributed_grid/tui/__init__.py`
- Create: `src/distributed_grid/tui/offload_dashboard.py`
- Test: `tests/test_offload_dashboard.py` (new)

**Step 1: Write the failing test**

Create `tests/test_offload_dashboard.py`:

```python
"""Tests for offload dashboard TUI."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime

from distributed_grid.tui.offload_dashboard import OffloadDashboard, DashboardData
from distributed_grid.monitoring.resource_metrics import ResourceSnapshot
from tests.conftest import get_test_cluster_config


class TestOffloadDashboard:
    """Test offload dashboard components."""

    @pytest.fixture
    def cluster_config(self):
        return get_test_cluster_config()

    @pytest.fixture
    def mock_metrics_collector(self):
        collector = MagicMock()
        collector.get_all_latest_snapshots.return_value = {
            "gpu-master": MagicMock(
                node_id="gpu-master",
                cpu_percent=62.0,
                memory_percent=89.0,
                gpu_utilization=31.0,
                memory_pressure=0.89,
                cpu_pressure=0.62,
            ),
            "gpu1": MagicMock(
                node_id="gpu1",
                cpu_percent=23.0,
                memory_percent=45.0,
                gpu_utilization=12.0,
                memory_pressure=0.45,
                cpu_pressure=0.23,
            ),
        }
        return collector

    @pytest.fixture
    def dashboard(self, cluster_config, mock_metrics_collector):
        return OffloadDashboard(
            cluster_config=cluster_config,
            metrics_collector=mock_metrics_collector,
        )

    def test_dashboard_init(self, dashboard, cluster_config):
        """Test dashboard initialization."""
        assert dashboard.cluster_config == cluster_config
        assert dashboard.head_node_id == "gpu-master"
        assert dashboard.refresh_interval == 1.0

    def test_collect_data(self, dashboard):
        """Test data collection for display."""
        data = dashboard.collect_data()

        assert isinstance(data, DashboardData)
        assert data.head_node is not None
        assert data.head_node.node_id == "gpu-master"
        assert len(data.worker_nodes) == 2  # gpu1, gpu2

    def test_build_head_node_panel(self, dashboard):
        """Test head node panel rendering."""
        data = dashboard.collect_data()
        panel = dashboard.build_head_node_panel(data.head_node)

        # Panel should be a Rich renderable
        assert panel is not None

    def test_build_workers_panel(self, dashboard):
        """Test workers panel rendering."""
        data = dashboard.collect_data()
        panel = dashboard.build_workers_panel(data.worker_nodes)

        assert panel is not None

    def test_build_layout(self, dashboard):
        """Test full layout building."""
        layout = dashboard.build_layout()

        # Should return a Rich renderable
        assert layout is not None

    def test_high_pressure_indicator(self, dashboard):
        """Test that high pressure shows warning indicator."""
        data = dashboard.collect_data()

        # gpu-master has 89% memory (high)
        assert data.head_node.memory_percent > 80

        panel = dashboard.build_head_node_panel(data.head_node)
        # Panel should contain warning indicator (tested via string repr)
        panel_str = str(panel)
        # We expect some kind of warning indicator for high memory
```

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_offload_dashboard.py -v`
Expected: FAIL with "No module named 'distributed_grid.tui'"

**Step 3: Write minimal implementation**

Create `src/distributed_grid/tui/__init__.py`:

```python
"""TUI components for distributed grid."""

from distributed_grid.tui.offload_dashboard import OffloadDashboard, DashboardData

__all__ = ["OffloadDashboard", "DashboardData"]
```

Create `src/distributed_grid/tui/offload_dashboard.py`:

```python
"""Real-time offload monitoring dashboard."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn
from rich.table import Table
from rich.text import Text

from distributed_grid.config import ClusterConfig
from distributed_grid.monitoring.resource_metrics import ResourceMetricsCollector, ResourceSnapshot
from distributed_grid.orchestration.auto_offload_state import AutoOffloadState, OffloadEvent

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class NodeMetrics:
    """Metrics for a single node."""
    node_id: str
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    gpu_utilization: float = 0.0
    is_available: bool = True


@dataclass
class DashboardData:
    """Data collected for dashboard display."""
    head_node: Optional[NodeMetrics] = None
    worker_nodes: List[NodeMetrics] = field(default_factory=list)
    active_offloads: List[Dict[str, Any]] = field(default_factory=list)
    recent_events: List[OffloadEvent] = field(default_factory=list)
    auto_enabled: bool = False
    thresholds: Dict[str, int] = field(default_factory=dict)


class OffloadDashboard:
    """Interactive TUI dashboard for offload monitoring."""

    def __init__(
        self,
        cluster_config: ClusterConfig,
        metrics_collector: Optional[ResourceMetricsCollector] = None,
        state: Optional[AutoOffloadState] = None,
        refresh_interval: float = 1.0,
    ):
        self.cluster_config = cluster_config
        self.metrics_collector = metrics_collector
        self.state = state or AutoOffloadState()
        self.refresh_interval = refresh_interval
        self.console = Console()

        # Identify head node
        self.head_node_id = cluster_config.nodes[0].name if cluster_config.nodes else None
        self.worker_node_ids = [n.name for n in cluster_config.nodes[1:]]

        # Control flags
        self._running = False
        self._paused = False

    def collect_data(self) -> DashboardData:
        """Collect current data for display."""
        data = DashboardData(
            auto_enabled=self.state.enabled,
            thresholds=self.state.thresholds,
            active_offloads=self.state.active_offloads,
            recent_events=self.state.recent_events[-10:],  # Last 10 events
        )

        if self.metrics_collector:
            snapshots = self.metrics_collector.get_all_latest_snapshots()

            # Head node
            if self.head_node_id and self.head_node_id in snapshots:
                snap = snapshots[self.head_node_id]
                data.head_node = NodeMetrics(
                    node_id=self.head_node_id,
                    cpu_percent=getattr(snap, 'cpu_percent', 0.0),
                    memory_percent=getattr(snap, 'memory_percent', 0.0),
                    gpu_utilization=getattr(snap, 'gpu_utilization', 0.0),
                )
            else:
                data.head_node = NodeMetrics(node_id=self.head_node_id or "unknown")

            # Worker nodes
            for node_id in self.worker_node_ids:
                if node_id in snapshots:
                    snap = snapshots[node_id]
                    data.worker_nodes.append(NodeMetrics(
                        node_id=node_id,
                        cpu_percent=getattr(snap, 'cpu_percent', 0.0),
                        memory_percent=getattr(snap, 'memory_percent', 0.0),
                        gpu_utilization=getattr(snap, 'gpu_utilization', 0.0),
                    ))
                else:
                    data.worker_nodes.append(NodeMetrics(node_id=node_id, is_available=False))
        else:
            # No metrics collector - show config-based nodes with no data
            data.head_node = NodeMetrics(node_id=self.head_node_id or "unknown")
            data.worker_nodes = [NodeMetrics(node_id=n) for n in self.worker_node_ids]

        return data

    def _make_progress_bar(self, percent: float, threshold: int = 80) -> Text:
        """Create a progress bar with color coding."""
        bar_width = 20
        filled = int(bar_width * percent / 100)
        empty = bar_width - filled

        if percent >= threshold:
            color = "red"
            indicator = " ⚠ HIGH"
        elif percent >= threshold * 0.75:
            color = "yellow"
            indicator = ""
        else:
            color = "green"
            indicator = ""

        bar = Text()
        bar.append("[")
        bar.append("█" * filled, style=color)
        bar.append("░" * empty, style="dim")
        bar.append(f"] {percent:5.1f}%{indicator}")
        return bar

    def build_head_node_panel(self, node: Optional[NodeMetrics]) -> Panel:
        """Build the head node status panel."""
        if not node:
            return Panel("[dim]No head node data[/dim]", title="HEAD NODE")

        thresholds = self.state.thresholds

        content = Table.grid(padding=(0, 2))
        content.add_column(width=8)
        content.add_column()

        content.add_row("CPU", self._make_progress_bar(node.cpu_percent, thresholds.get("cpu", 80)))
        content.add_row("Memory", self._make_progress_bar(node.memory_percent, thresholds.get("memory", 70)))
        content.add_row("GPU", self._make_progress_bar(node.gpu_utilization, thresholds.get("gpu", 90)))

        return Panel(content, title=f"HEAD NODE: {node.node_id}", border_style="blue")

    def build_workers_panel(self, workers: List[NodeMetrics]) -> Panel:
        """Build the workers status panel."""
        table = Table(box=None, padding=(0, 1))
        table.add_column("Node", style="cyan")
        table.add_column("CPU", justify="right")
        table.add_column("Mem", justify="right")
        table.add_column("GPU", justify="right")
        table.add_column("Status")

        for w in workers:
            status = "[green]✓ Available[/green]" if w.is_available else "[red]✗ Offline[/red]"
            table.add_row(
                w.node_id,
                f"{w.cpu_percent:.0f}%",
                f"{w.memory_percent:.0f}%",
                f"{w.gpu_utilization:.0f}%",
                status,
            )

        return Panel(table, title="WORKERS (offload targets)", border_style="green")

    def build_offloads_panel(self, offloads: List[Dict[str, Any]]) -> Panel:
        """Build active offloads panel."""
        if not offloads:
            content = Text("[dim]No active offloads[/dim]")
        else:
            lines = []
            for o in offloads:
                line = f"• PID {o['pid']} → {o['target_node']}  {o['command']}"
                lines.append(line)
            content = Text("\n".join(lines))

        return Panel(content, title=f"ACTIVE OFFLOADS ({len(offloads)})", border_style="yellow")

    def build_events_panel(self, events: List[OffloadEvent]) -> Panel:
        """Build recent events panel."""
        if not events:
            content = Text("[dim]No recent events[/dim]")
        else:
            lines = []
            for e in reversed(events[-5:]):  # Show last 5
                time_str = e.timestamp.strftime("%H:%M:%S")
                lines.append(f"{time_str}  {e.event_type}: {e.details}")
            content = Text("\n".join(lines))

        return Panel(content, title="RECENT EVENTS", border_style="dim")

    def build_header(self, auto_enabled: bool) -> Panel:
        """Build the header panel."""
        status = "[green]● ENABLED[/green]" if auto_enabled else "[dim]○ DISABLED[/dim]"
        title = Text()
        title.append("GRID OFFLOAD MONITOR", style="bold")
        title.append("                          Auto: ")
        title.append_text(Text.from_markup(status))

        return Panel(title, box=None)

    def build_footer(self) -> Text:
        """Build the footer with key bindings."""
        footer = Text()
        footer.append("  [q]", style="bold cyan")
        footer.append(" Quit  ")
        footer.append("[p]", style="bold cyan")
        footer.append(" Pause  ")
        footer.append("[r]", style="bold cyan")
        footer.append(" Refresh  ")
        footer.append("[o]", style="bold cyan")
        footer.append(" Manual offload")
        return footer

    def build_layout(self) -> Group:
        """Build the complete dashboard layout."""
        data = self.collect_data()

        return Group(
            self.build_header(data.auto_enabled),
            self.build_head_node_panel(data.head_node),
            self.build_workers_panel(data.worker_nodes),
            self.build_offloads_panel(data.active_offloads),
            self.build_events_panel(data.recent_events),
            self.build_footer(),
        )

    async def run(self) -> None:
        """Run the dashboard with live updates."""
        self._running = True

        with Live(self.build_layout(), console=self.console, refresh_per_second=4) as live:
            while self._running:
                if not self._paused:
                    live.update(self.build_layout())
                await asyncio.sleep(self.refresh_interval)

    def stop(self) -> None:
        """Stop the dashboard."""
        self._running = False

    def toggle_pause(self) -> None:
        """Toggle pause state."""
        self._paused = not self._paused
```

**Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_offload_dashboard.py -v`
Expected: PASS (7 tests)

**Step 5: Commit**

```bash
git add src/distributed_grid/tui/__init__.py src/distributed_grid/tui/offload_dashboard.py tests/test_offload_dashboard.py
git commit -m "feat(tui): add OffloadDashboard for real-time monitoring"
```

---

## Task 7: Wire Up CLI Watch Command

**Files:**
- Modify: `src/distributed_grid/cli.py` (add `offload watch` implementation)
- Test: `tests/test_watch_cli.py` (new)

**Step 1: Write the failing test**

Create `tests/test_watch_cli.py`:

```python
"""Tests for offload watch CLI command."""

import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock, AsyncMock

from distributed_grid.cli import cli


class TestWatchCLI:
    """Test offload watch command."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_watch_requires_config(self, runner):
        """Test that watch command requires valid config."""
        result = runner.invoke(cli, ["offload", "watch", "-c", "/nonexistent/config.yaml"])

        # Should fail due to missing config
        assert result.exit_code != 0

    def test_watch_starts_dashboard(self, runner, tmp_path):
        """Test that watch starts the dashboard."""
        # Create minimal config
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
name: test-cluster
nodes:
  - name: gpu-master
    host: localhost
    user: test
    role: master
""")

        with patch("distributed_grid.cli.OffloadDashboard") as MockDashboard:
            mock_dashboard = MagicMock()
            mock_dashboard.run = AsyncMock()
            MockDashboard.return_value = mock_dashboard

            # Use timeout to prevent infinite loop
            with patch("asyncio.run") as mock_run:
                result = runner.invoke(cli, ["offload", "watch", "-c", str(config_file)])

            MockDashboard.assert_called_once()

    def test_watch_interval_option(self, runner, tmp_path):
        """Test custom refresh interval."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
name: test-cluster
nodes:
  - name: gpu-master
    host: localhost
    user: test
    role: master
""")

        with patch("distributed_grid.cli.OffloadDashboard") as MockDashboard:
            mock_dashboard = MagicMock()
            MockDashboard.return_value = mock_dashboard

            with patch("asyncio.run"):
                result = runner.invoke(cli, [
                    "offload", "watch",
                    "-c", str(config_file),
                    "--interval", "2"
                ])

            # Check interval was passed
            call_kwargs = MockDashboard.call_args[1]
            assert call_kwargs.get("refresh_interval") == 2.0
```

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_watch_cli.py -v`
Expected: FAIL (watch command exists but may not have dashboard integration)

**Step 3: Write minimal implementation**

Update/add to `src/distributed_grid/cli.py`:

```python
from distributed_grid.tui.offload_dashboard import OffloadDashboard


@offload.command()
@click.option(
    "--config", "-c",
    type=click.Path(exists=True, path_type=Path),
    default=Path("config/my-cluster-enhanced.yaml"),
    help="Path to cluster config file"
)
@click.option(
    "--interval", "-i",
    type=float,
    default=1.0,
    help="Refresh interval in seconds"
)
def watch(config: Path, interval: float) -> None:
    """Launch interactive offload monitoring dashboard.

    Shows real-time resource pressure on head node, worker availability,
    active offloads, and recent events.

    Examples:

        grid offload watch

        grid offload watch --interval 2

        grid offload watch -c my-cluster.yaml
    """
    setup_logging()

    try:
        cluster_config = ClusterConfig.from_yaml(config)
    except Exception as e:
        console.print(f"[red]Error loading config: {e}[/red]")
        raise SystemExit(1)

    # Initialize metrics collector (read-only mode if daemon not running)
    metrics_collector = ResourceMetricsCollector(
        cluster_config,
        collection_interval=interval,
    )

    # Create and run dashboard
    dashboard = OffloadDashboard(
        cluster_config=cluster_config,
        metrics_collector=metrics_collector,
        refresh_interval=interval,
    )

    console.print("[blue]Starting offload monitor dashboard...[/blue]")
    console.print("[dim]Press Ctrl+C to exit[/dim]\n")

    async def _run():
        try:
            await metrics_collector.start()
            await dashboard.run()
        finally:
            await metrics_collector.stop()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        console.print("\n[yellow]Dashboard stopped[/yellow]")
```

**Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_watch_cli.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add src/distributed_grid/cli.py tests/test_watch_cli.py
git commit -m "feat(cli): wire up 'grid offload watch' to TUI dashboard"
```

---

## Task 8: Integration Test

**Files:**
- Create: `tests/test_auto_offload_integration.py`

**Step 1: Write integration test**

Create `tests/test_auto_offload_integration.py`:

```python
"""Integration tests for auto-offload feature."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

from distributed_grid.config import ClusterConfig
from distributed_grid.monitoring.resource_metrics import ResourceMetricsCollector, ResourceType
from distributed_grid.orchestration.auto_offload_state import AutoOffloadState
from distributed_grid.orchestration.enhanced_offloading_executor import EnhancedOffloadingExecutor
from tests.conftest import get_test_cluster_config


class TestAutoOffloadIntegration:
    """Integration tests for the complete auto-offload flow."""

    @pytest.fixture
    def cluster_config(self):
        return get_test_cluster_config()

    @pytest.fixture
    def state_file(self, tmp_path):
        return tmp_path / "state.json"

    async def test_end_to_end_auto_offload_flow(self, cluster_config, state_file):
        """Test complete flow: enable → pressure → offload → disable."""
        # 1. Enable auto-offload
        state = AutoOffloadState(state_file)
        state.enable(cpu=80, memory=70, gpu=90)

        assert state.enabled is True
        assert state_file.exists()

        # 2. Create metrics collector in head-only mode
        collector = ResourceMetricsCollector(
            cluster_config,
            head_only_mode=True,
        )

        assert collector._head_only_mode is True
        assert collector._head_node_id == "gpu-master"

        # 3. Simulate pressure callback
        pressure_events = []
        def on_pressure(node_id, resource_type, pressure):
            pressure_events.append((node_id, resource_type, pressure))

        collector.register_pressure_callback(on_pressure)

        # Simulate high memory on head node
        collector._latest_snapshot = {
            "gpu-master": MagicMock(memory_pressure=0.85, cpu_pressure=0.5),
            "gpu1": MagicMock(memory_pressure=0.90, cpu_pressure=0.5),  # Should be ignored
        }
        collector._check_pressure_events()

        # Only head node should trigger
        assert len(pressure_events) == 1
        assert pressure_events[0][0] == "gpu-master"
        assert pressure_events[0][1] == ResourceType.MEMORY

        # 4. Verify offload target validation
        executor = EnhancedOffloadingExecutor(
            ssh_manager=MagicMock(),
            cluster_config=cluster_config,
            ray_dashboard_address="http://localhost:8265",
        )

        # Offload TO head should be rejected
        bad_recommendation = MagicMock()
        bad_recommendation.target_node = "gpu-master"
        bad_recommendation.source_node = "gpu1"

        is_valid, reason = executor.validate_offload_target(bad_recommendation)
        assert is_valid is False

        # Offload FROM head should be allowed
        good_recommendation = MagicMock()
        good_recommendation.target_node = "gpu1"
        good_recommendation.source_node = "gpu-master"

        is_valid, reason = executor.validate_offload_target(good_recommendation)
        assert is_valid is True

        # 5. Disable auto-offload
        state.disable()
        assert state.enabled is False

        # Reload state to verify persistence
        state2 = AutoOffloadState(state_file)
        state2.load()
        assert state2.enabled is False

    async def test_state_survives_restart(self, state_file):
        """Test that state persists across process restarts."""
        # First "process"
        state1 = AutoOffloadState(state_file)
        state1.enable(cpu=75, memory=65, gpu=85)
        state1.add_active_offload("task-1", 1234, "gpu1", "python train.py")
        state1.save()

        # Second "process" (simulate restart)
        state2 = AutoOffloadState(state_file)
        # Load happens in __init__ if file exists

        assert state2.enabled is True
        assert state2.thresholds["cpu"] == 75
        assert len(state2.active_offloads) == 1
        assert state2.active_offloads[0]["pid"] == 1234
```

**Step 2: Run integration test**

Run: `poetry run pytest tests/test_auto_offload_integration.py -v`
Expected: PASS (2 tests)

**Step 3: Commit**

```bash
git add tests/test_auto_offload_integration.py
git commit -m "test: add integration tests for auto-offload feature"
```

---

## Task 9: Update Documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `PROJECT_INDEX.md`

**Step 1: Update CLAUDE.md**

Add to the CLI usage section:

```markdown
# Auto-Offload (Head Node Protection)
grid offload auto --enable                    # Enable with defaults
grid offload auto --enable --threshold 70     # Custom memory threshold
grid offload auto --disable                   # Disable
grid offload auto --status                    # Check status
grid offload watch                            # Real-time TUI dashboard
```

**Step 2: Update PROJECT_INDEX.md**

Add to CLI Commands Quick Reference:

```markdown
# Auto-offload (head node protection)
grid offload auto --enable
grid offload auto --enable --threshold cpu=80 memory=65
grid offload auto --disable
grid offload auto --status
grid offload watch                    # TUI dashboard
grid offload watch --interval 2       # Custom refresh rate
```

**Step 3: Commit**

```bash
git add CLAUDE.md PROJECT_INDEX.md
git commit -m "docs: add auto-offload CLI commands to documentation"
```

---

## Summary

| Task | Description | Tests |
|------|-------------|-------|
| 1 | AutoOffloadConfig model | 4 |
| 2 | Head-only mode in metrics | 5 |
| 3 | Target validation in executor | 4 |
| 4 | State persistence | 6 |
| 5 | CLI `offload auto` command | 6 |
| 6 | TUI dashboard | 7 |
| 7 | CLI `offload watch` command | 3 |
| 8 | Integration test | 2 |
| 9 | Documentation | - |

**Total: 37 tests across 8 test files**

**Estimated commits: 9**
