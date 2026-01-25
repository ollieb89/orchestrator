"""Tests for TUI offload dashboard."""

from __future__ import annotations

from datetime import datetime
from io import StringIO

import pytest
from rich.console import Console

from distributed_grid.orchestration.auto_offload_state import (
    AutoOffloadState,
    OffloadEvent,
)
from distributed_grid.tui.offload_dashboard import OffloadDashboard


class TestOffloadDashboard:
    """Test TUI dashboard for offload monitoring."""

    @pytest.fixture
    def state_file(self, tmp_path):
        return tmp_path / "offload_state.json"

    @pytest.fixture
    def state_manager(self, state_file):
        return AutoOffloadState(state_file)

    @pytest.fixture
    def test_console(self):
        """Create a console that writes to a string buffer for testing."""
        return Console(file=StringIO(), force_terminal=True, width=80)

    @pytest.fixture
    def dashboard(self, state_manager, test_console):
        return OffloadDashboard(
            state=state_manager,
            refresh_interval=1.0,
            console=test_console,
        )

    def test_dashboard_init(self, state_manager, test_console):
        """Test dashboard initializes correctly."""
        dashboard = OffloadDashboard(
            state=state_manager,
            refresh_interval=2.0,
            console=test_console,
        )

        assert dashboard.state is state_manager
        assert dashboard.refresh_interval == 2.0
        assert dashboard.console is test_console
        assert dashboard._running is False
        assert dashboard._paused is False

    def test_build_header_enabled(self, dashboard, state_manager):
        """Test header shows enabled status."""
        state_manager.enable(cpu=80, memory=70, gpu=90)

        header = dashboard.build_header()

        # Render the panel to check content
        console = Console(file=StringIO(), force_terminal=True, width=80)
        console.print(header)
        output = console.file.getvalue()

        assert "GRID OFFLOAD MONITOR" in output
        assert "ENABLED" in output

    def test_build_header_disabled(self, dashboard, state_manager):
        """Test header shows disabled status."""
        state_manager.disable()

        header = dashboard.build_header()

        console = Console(file=StringIO(), force_terminal=True, width=80)
        console.print(header)
        output = console.file.getvalue()

        assert "GRID OFFLOAD MONITOR" in output
        assert "DISABLED" in output

    def test_build_head_node_panel(self, dashboard):
        """Test head node panel renders with metrics."""
        panel = dashboard.build_head_node_panel()

        console = Console(file=StringIO(), force_terminal=True, width=80)
        console.print(panel)
        output = console.file.getvalue()

        # Should show head node section with CPU, Memory, GPU bars
        assert "HEAD NODE" in output
        assert "CPU" in output
        assert "Memory" in output
        assert "GPU" in output

    def test_build_workers_panel(self, dashboard):
        """Test workers panel renders with worker info."""
        panel = dashboard.build_workers_panel()

        console = Console(file=StringIO(), force_terminal=True, width=80)
        console.print(panel)
        output = console.file.getvalue()

        # Should show workers section
        assert "WORKERS" in output

    def test_build_active_offloads_panel(self, dashboard, state_manager):
        """Test active offloads display correctly."""
        # Add some active offloads
        state_manager.add_active_offload(
            task_id="task-123",
            pid=4521,
            target_node="gpu1",
            command="python train.py",
        )
        state_manager.add_active_offload(
            task_id="task-456",
            pid=4892,
            target_node="gpu2",
            command="jupyter kernel",
        )

        panel = dashboard.build_active_offloads_panel()

        console = Console(file=StringIO(), force_terminal=True, width=80)
        console.print(panel)
        output = console.file.getvalue()

        # Should show active offloads
        assert "ACTIVE OFFLOADS" in output
        assert "4521" in output
        assert "gpu1" in output
        assert "train.py" in output
        assert "4892" in output
        assert "gpu2" in output

    def test_build_events_panel(self, dashboard, state_manager):
        """Test events display correctly."""
        # Add some events
        state_manager.add_event(
            OffloadEvent(
                timestamp=datetime(2024, 1, 15, 14, 32, 1),
                event_type="pressure_detected",
                node_id="gpu-master",
                details={"memory": 0.89},
            )
        )
        state_manager.add_event(
            OffloadEvent(
                timestamp=datetime(2024, 1, 15, 14, 32, 3),
                event_type="offload_started",
                node_id="gpu1",
                details={"pid": 4521, "command": "train.py"},
            )
        )

        panel = dashboard.build_events_panel()

        console = Console(file=StringIO(), force_terminal=True, width=80)
        console.print(panel)
        output = console.file.getvalue()

        # Should show recent events
        assert "RECENT EVENTS" in output
        assert "14:32:01" in output
        assert "pressure" in output.lower() or "Memory" in output
        assert "14:32:03" in output
