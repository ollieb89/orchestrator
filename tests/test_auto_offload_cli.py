"""Tests for auto-offload CLI commands."""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from distributed_grid.cli import cli, parse_threshold


runner = CliRunner()


class TestParseThreshold:
    """Tests for parse_threshold helper function."""

    def test_parse_threshold_single_value(self) -> None:
        """Test parsing a single threshold value applies to memory."""
        result = parse_threshold(("70",))

        assert result == {"cpu": 80, "memory": 70, "gpu": 90}

    def test_parse_threshold_key_value_pairs(self) -> None:
        """Test parsing key=value pairs for thresholds."""
        result = parse_threshold(("cpu=80", "memory=65", "gpu=90"))

        assert result == {"cpu": 80, "memory": 65, "gpu": 90}

    def test_parse_threshold_partial_key_value(self) -> None:
        """Test parsing only some key=value pairs uses defaults for others."""
        result = parse_threshold(("memory=50",))

        assert result == {"cpu": 80, "memory": 50, "gpu": 90}

    def test_parse_threshold_empty(self) -> None:
        """Test parsing empty threshold returns defaults."""
        result = parse_threshold(())

        assert result == {"cpu": 80, "memory": 70, "gpu": 90}


class TestAutoOffloadCommands:
    """Tests for auto-offload CLI commands."""

    def test_auto_enable_default_threshold(self) -> None:
        """Test enabling auto-offload with default threshold."""
        with patch("distributed_grid.cli.AutoOffloadState") as mock_state_class:
            mock_state = mock_state_class.return_value
            mock_state.enabled = False
            mock_state.thresholds = {"cpu": 80, "memory": 70, "gpu": 90}

            result = runner.invoke(cli, ["offload", "auto", "--enable"])

            assert result.exit_code == 0
            assert "enabled" in result.output.lower()
            mock_state.enable.assert_called_once()

    def test_auto_enable_custom_threshold(self) -> None:
        """Test enabling auto-offload with custom thresholds."""
        with patch("distributed_grid.cli.AutoOffloadState") as mock_state_class:
            mock_state = mock_state_class.return_value
            mock_state.enabled = False
            mock_state.thresholds = {"cpu": 80, "memory": 70, "gpu": 90}

            result = runner.invoke(
                cli,
                ["offload", "auto", "--enable", "--threshold", "cpu=85", "--threshold", "memory=60"]
            )

            assert result.exit_code == 0
            assert "enabled" in result.output.lower()
            # Verify enable was called with custom thresholds
            mock_state.enable.assert_called_once()
            call_kwargs = mock_state.enable.call_args
            # Should have cpu=85, memory=60, gpu=90 (default)
            assert call_kwargs[1].get("cpu") == 85 or call_kwargs[0][0] == 85
            assert call_kwargs[1].get("memory") == 60 or call_kwargs[0][1] == 60

    def test_auto_disable(self) -> None:
        """Test disabling auto-offload."""
        with patch("distributed_grid.cli.AutoOffloadState") as mock_state_class:
            mock_state = mock_state_class.return_value
            mock_state.enabled = True

            result = runner.invoke(cli, ["offload", "auto", "--disable"])

            assert result.exit_code == 0
            assert "disabled" in result.output.lower()
            mock_state.disable.assert_called_once()

    def test_auto_status(self) -> None:
        """Test showing auto-offload status."""
        with patch("distributed_grid.cli.AutoOffloadState") as mock_state_class:
            mock_state = mock_state_class.return_value
            mock_state.enabled = True
            mock_state.thresholds = {"cpu": 85, "memory": 60, "gpu": 90}
            mock_state.active_offloads = []
            mock_state.recent_events = []

            result = runner.invoke(cli, ["offload", "auto", "--status"])

            assert result.exit_code == 0
            assert "enabled" in result.output.lower() or "status" in result.output.lower()
            # Check that threshold values are displayed
            assert "85" in result.output or "cpu" in result.output.lower()
