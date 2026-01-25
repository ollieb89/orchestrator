"""Tests for auto-offload state persistence."""

from datetime import datetime

import pytest

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

        # Load in new instance (load is called automatically in __init__)
        loaded = AutoOffloadState(state_file)

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

    def test_corrupted_state_file(self, state_file):
        """Test that load() handles invalid JSON gracefully."""
        # Write invalid JSON to state file
        state_file.write_text("{ invalid json }")

        # Should not raise, should use defaults
        state_manager = AutoOffloadState(state_file)

        assert state_manager.enabled is False
        assert state_manager.thresholds == {"cpu": 80, "memory": 70, "gpu": 90}
        assert state_manager.active_offloads == []
        assert state_manager.recent_events == []
