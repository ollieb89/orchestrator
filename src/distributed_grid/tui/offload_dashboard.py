"""TUI dashboard for monitoring auto-offload operations."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from distributed_grid.orchestration.auto_offload_state import AutoOffloadState

logger = structlog.get_logger(__name__)


class OffloadDashboard:
    """Interactive TUI dashboard for monitoring auto-offload.

    Displays real-time information about:
    - Head node resource metrics (CPU, memory, GPU)
    - Worker node statuses and availability
    - Active offload operations
    - Recent events and alerts
    """

    def __init__(
        self,
        state: AutoOffloadState,
        refresh_interval: float = 1.0,
        console: Optional[Console] = None,
    ):
        """Initialize dashboard.

        Args:
            state: AutoOffloadState for reading enabled status, events, etc.
            refresh_interval: Seconds between refreshes
            console: Optional Rich console (for testing)
        """
        self.state = state
        self.refresh_interval = refresh_interval
        self.console = console or Console()
        self._running = False
        self._paused = False

        # Mock metrics for now (will be replaced with real metrics in Task 7)
        self._head_metrics: Dict[str, float] = {
            "cpu": 62.0,
            "memory": 89.0,
            "gpu": 31.0,
        }
        self._worker_metrics: List[Dict[str, Any]] = [
            {
                "name": "gpu1",
                "cpu": 23.0,
                "memory": 45.0,
                "gpu": 12.0,
                "available": True,
            },
            {
                "name": "gpu2",
                "cpu": 67.0,
                "memory": 52.0,
                "gpu": 88.0,
                "available": True,
            },
        ]

    def set_head_metrics(self, cpu: float, memory: float, gpu: float) -> None:
        """Set head node metrics (for testing or external updates).

        Args:
            cpu: CPU usage percentage (0-100)
            memory: Memory usage percentage (0-100)
            gpu: GPU usage percentage (0-100)
        """
        self._head_metrics = {"cpu": cpu, "memory": memory, "gpu": gpu}

    def set_worker_metrics(self, workers: List[Dict[str, Any]]) -> None:
        """Set worker metrics (for testing or external updates).

        Args:
            workers: List of worker metric dicts with keys:
                     name, cpu, memory, gpu, available
        """
        self._worker_metrics = workers

    def build_layout(self) -> Layout:
        """Build the complete dashboard layout."""
        layout = Layout()

        layout.split_column(
            Layout(self.build_header(), name="header", size=3),
            Layout(self.build_head_node_panel(), name="head_node", size=7),
            Layout(self.build_workers_panel(), name="workers", size=5),
            Layout(self.build_active_offloads_panel(), name="offloads", size=6),
            Layout(self.build_events_panel(), name="events", size=7),
            Layout(self.build_footer(), name="footer", size=1),
        )

        return layout

    def build_header(self) -> Panel:
        """Build header showing title and auto-offload status."""
        status_indicator = (
            "[green bold]ENABLED[/]" if self.state.enabled else "[red bold]DISABLED[/]"
        )
        status_dot = "[green]\u25cf[/]" if self.state.enabled else "[red]\u25cf[/]"

        header_text = Text()
        header_text.append("  GRID OFFLOAD MONITOR", style="bold cyan")
        header_text.append(" " * 30)
        header_text.append(f"Auto: {status_dot} {status_indicator}")

        return Panel(header_text, style="blue")

    def build_head_node_panel(self) -> Panel:
        """Build panel showing head node metrics."""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Resource", width=8)
        table.add_column("Bar", width=40)
        table.add_column("Percent", width=6)
        table.add_column("Status", width=10)

        # CPU row
        cpu_pct = self._head_metrics["cpu"]
        cpu_bar = self._build_progress_bar(cpu_pct)
        cpu_status = self._get_status_indicator(cpu_pct, warning_threshold=80)
        table.add_row("CPU", cpu_bar, f"{cpu_pct:.0f}%", cpu_status)

        # Memory row
        mem_pct = self._head_metrics["memory"]
        mem_bar = self._build_progress_bar(mem_pct)
        mem_status = self._get_status_indicator(mem_pct, warning_threshold=70)
        table.add_row("Memory", mem_bar, f"{mem_pct:.0f}%", mem_status)

        # GPU row
        gpu_pct = self._head_metrics["gpu"]
        gpu_bar = self._build_progress_bar(gpu_pct)
        gpu_status = self._get_status_indicator(gpu_pct, warning_threshold=90)
        table.add_row("GPU", gpu_bar, f"{gpu_pct:.0f}%", gpu_status)

        return Panel(
            table,
            title="[bold]HEAD NODE: gpu-master[/]",
            border_style="green",
        )

    def _build_progress_bar(self, percentage: float) -> Text:
        """Build a text-based progress bar."""
        total_width = 20
        filled = int(percentage / 100 * total_width)
        empty = total_width - filled

        # Color based on percentage
        if percentage >= 90:
            color = "red"
        elif percentage >= 70:
            color = "yellow"
        else:
            color = "green"

        bar = Text()
        bar.append("[")
        bar.append("\u2588" * filled, style=color)
        bar.append("\u2591" * empty, style="dim")
        bar.append("]")

        return bar

    def _get_status_indicator(
        self, percentage: float, warning_threshold: float = 80
    ) -> Text:
        """Get status indicator based on percentage."""
        if percentage >= 90:
            return Text("\u26a0 HIGH", style="red bold")
        elif percentage >= warning_threshold:
            return Text("\u26a0 HIGH", style="yellow bold")
        else:
            return Text("", style="green")

    def build_workers_panel(self) -> Panel:
        """Build panel showing worker statuses."""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Worker", width=8)
        table.add_column("CPU", width=10)
        table.add_column("Mem", width=10)
        table.add_column("GPU", width=10)
        table.add_column("Status", width=15)

        for worker in self._worker_metrics:
            name = worker["name"]
            cpu = f"CPU {worker['cpu']:.0f}%"
            mem = f"Mem {worker['memory']:.0f}%"
            gpu = f"GPU {worker['gpu']:.0f}%"

            if worker["available"]:
                status = Text("\u2713 Available", style="green")
            else:
                status = Text("\u2717 Busy", style="yellow")

            table.add_row(f"{name}:", cpu, mem, gpu, status)

        if not self._worker_metrics:
            table.add_row("No workers configured", "", "", "", "")

        return Panel(
            table,
            title="[bold]WORKERS (offload targets)[/]",
            border_style="blue",
        )

    def build_active_offloads_panel(self) -> Panel:
        """Build panel showing active offloads."""
        offloads = self.state.active_offloads
        count = len(offloads)

        lines = []
        for offload in offloads:
            pid = offload.get("pid", "?")
            target = offload.get("target_node", "?")
            command = offload.get("command", "unknown")
            started_at = offload.get("started_at", "")

            # Calculate runtime if we have a start time
            runtime = self._calculate_runtime(started_at)

            # Truncate command if too long
            if len(command) > 20:
                command = command[:17] + "..."

            line = Text()
            line.append("  \u2022 ", style="cyan")
            line.append(f"PID {pid}", style="bold")
            line.append(" \u2192 ", style="dim")
            line.append(f"{target}", style="green")
            line.append(f"  {command}", style="white")
            line.append(f"      Running {runtime}", style="dim")
            lines.append(line)

        if not offloads:
            lines.append(Text("  No active offloads", style="dim"))

        content = Text("\n").join(lines)

        return Panel(
            content,
            title=f"[bold]ACTIVE OFFLOADS ({count})[/]",
            border_style="yellow",
        )

    def _calculate_runtime(self, started_at: str) -> str:
        """Calculate runtime from start time."""
        if not started_at:
            return "0s"

        try:
            start = datetime.fromisoformat(started_at)
            delta = datetime.now() - start
            total_seconds = int(delta.total_seconds())

            if total_seconds < 60:
                return f"{total_seconds}s"
            elif total_seconds < 3600:
                minutes = total_seconds // 60
                seconds = total_seconds % 60
                return f"{minutes}m {seconds}s"
            else:
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                return f"{hours}h {minutes}m"
        except (ValueError, TypeError):
            return "?"

    def build_events_panel(self) -> Panel:
        """Build panel showing recent events."""
        events = self.state.recent_events[-10:]  # Show last 10 events

        lines = []
        for event in reversed(events):  # Most recent first
            timestamp = event.timestamp.strftime("%H:%M:%S")
            description = self._format_event_description(event)

            line = Text()
            line.append(f"  {timestamp}  ", style="dim")
            line.append(description)
            lines.append(line)

        if not events:
            lines.append(Text("  No recent events", style="dim"))

        content = Text("\n").join(lines)

        return Panel(
            content,
            title="[bold]RECENT EVENTS[/]",
            border_style="magenta",
        )

    def _format_event_description(self, event) -> Text:
        """Format an event into a readable description."""
        text = Text()

        if event.event_type == "pressure_detected":
            memory_pct = event.details.get("memory", 0)
            if isinstance(memory_pct, float) and memory_pct < 1:
                memory_pct = int(memory_pct * 100)
            text.append(f"Memory pressure detected ({memory_pct}%)", style="yellow")
        elif event.event_type == "offload_started":
            pid = event.details.get("pid", "?")
            text.append(f"Offloaded PID {pid} to {event.node_id}", style="green")
        elif event.event_type == "offload_completed":
            pid = event.details.get("pid", "?")
            text.append(f"Offload completed: PID {pid}", style="green")
        elif event.event_type == "offload_failed":
            pid = event.details.get("pid", "?")
            error = event.details.get("error", "unknown error")
            text.append(f"Offload failed: PID {pid} - {error}", style="red")
        else:
            text.append(f"{event.event_type}: {event.node_id}", style="white")

        return text

    def build_footer(self) -> Text:
        """Build footer with key bindings."""
        footer = Text()
        footer.append("  [q]", style="bold cyan")
        footer.append(" Quit  ", style="dim")
        footer.append("[p]", style="bold cyan")
        footer.append(" Pause  ", style="dim")
        footer.append("[r]", style="bold cyan")
        footer.append(" Refresh now  ", style="dim")
        footer.append("[o]", style="bold cyan")
        footer.append(" Manual offload", style="dim")

        return footer

    async def run(self) -> None:
        """Run the interactive dashboard.

        This starts a Rich Live display that auto-refreshes at the
        configured interval. Keyboard input is handled for quit,
        pause, refresh, and manual offload commands.
        """
        self._running = True
        self._paused = False

        logger.info(
            "Starting offload dashboard", refresh_interval=self.refresh_interval
        )

        try:
            with Live(
                self.build_layout(),
                console=self.console,
                refresh_per_second=1 / self.refresh_interval,
                screen=True,
            ) as live:
                while self._running:
                    if not self._paused:
                        live.update(self.build_layout())

                    # Small sleep to prevent CPU spinning
                    await asyncio.sleep(self.refresh_interval)
        except KeyboardInterrupt:
            logger.info("Dashboard stopped by user")
        finally:
            self._running = False

    def stop(self) -> None:
        """Stop the dashboard."""
        self._running = False
        logger.info("Dashboard stopped")

    def pause(self) -> None:
        """Pause auto-refresh."""
        self._paused = True
        logger.info("Dashboard paused")

    def resume(self) -> None:
        """Resume auto-refresh."""
        self._paused = False
        logger.info("Dashboard resumed")

    def toggle_pause(self) -> None:
        """Toggle pause state."""
        if self._paused:
            self.resume()
        else:
            self.pause()
