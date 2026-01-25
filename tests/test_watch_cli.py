"""Tests for grid offload watch command."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from distributed_grid.cli import cli


runner = CliRunner()


class TestWatchCommand:
    """Tests for the offload watch command."""

    def test_watch_default_interval(self) -> None:
        """Test watch command with default 1 second interval."""
        with patch("distributed_grid.cli.AutoOffloadState") as mock_state_class, \
             patch("distributed_grid.cli.OffloadDashboard") as mock_dashboard_class:
            mock_state = MagicMock()
            mock_state_class.return_value = mock_state

            mock_dashboard = MagicMock()
            mock_dashboard.run = AsyncMock()
            mock_dashboard_class.return_value = mock_dashboard

            result = runner.invoke(cli, ["offload", "watch"])

            assert result.exit_code == 0
            # Verify dashboard was created with state and default interval
            mock_dashboard_class.assert_called_once_with(
                state=mock_state,
                refresh_interval=1.0,
            )
            # Verify run was called
            mock_dashboard.run.assert_called_once()

    def test_watch_custom_interval(self) -> None:
        """Test watch command with custom --interval option."""
        with patch("distributed_grid.cli.AutoOffloadState") as mock_state_class, \
             patch("distributed_grid.cli.OffloadDashboard") as mock_dashboard_class:
            mock_state = MagicMock()
            mock_state_class.return_value = mock_state

            mock_dashboard = MagicMock()
            mock_dashboard.run = AsyncMock()
            mock_dashboard_class.return_value = mock_dashboard

            result = runner.invoke(cli, ["offload", "watch", "--interval", "2"])

            assert result.exit_code == 0
            # Verify dashboard was created with custom interval
            mock_dashboard_class.assert_called_once_with(
                state=mock_state,
                refresh_interval=2.0,
            )
            mock_dashboard.run.assert_called_once()

    def test_watch_keyboard_interrupt(self) -> None:
        """Test watch command handles Ctrl+C gracefully."""
        with patch("distributed_grid.cli.AutoOffloadState") as mock_state_class, \
             patch("distributed_grid.cli.OffloadDashboard") as mock_dashboard_class:
            mock_state = MagicMock()
            mock_state_class.return_value = mock_state

            mock_dashboard = MagicMock()
            # Simulate KeyboardInterrupt when run() is called
            mock_dashboard.run = AsyncMock(side_effect=KeyboardInterrupt())
            mock_dashboard_class.return_value = mock_dashboard

            result = runner.invoke(cli, ["offload", "watch"])

            # Should exit cleanly (exit code 0) when interrupted
            assert result.exit_code == 0
            # Should show the stopped message
            assert "stopped" in result.output.lower() or "dashboard" in result.output.lower()
