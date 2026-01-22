"""Alerting system for cluster events."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional

from distributed_grid.schemas.node import NodeStatus


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Alert:
    """An alert event."""
    id: str
    severity: AlertSeverity
    title: str
    message: str
    source: str
    timestamp: datetime
    metadata: Optional[Dict] = None


class AlertManager:
    """Manages alerts and notifications."""

    def __init__(self) -> None:
        """Initialize the alert manager."""
        self._alerts: List[Alert] = []
        self._alert_handlers: List[Callable[[Alert], None]] = []
        self._alert_rules: Dict[str, Callable] = {}

    def register_handler(self, handler: Callable[[Alert], None]) -> None:
        """Register an alert handler."""
        self._alert_handlers.append(handler)

    def add_rule(self, name: str, condition: Callable) -> None:
        """Add an alert rule."""
        self._alert_rules[name] = condition

    async def process_node_status(self, node_id: str, status: NodeStatus) -> None:
        """Process node status and generate alerts if needed."""
        # Check for node down
        if status.status == "unhealthy":
            await self._create_alert(
                severity=AlertSeverity.ERROR,
                title=f"Node {node_id} is unhealthy",
                message=f"Node {node_id} reported unhealthy status",
                source=f"node:{node_id}",
                metadata={"node_id": node_id, "status": status.status},
            )
        
        # Check for high GPU utilization
        if status.gpu_utilization and status.gpu_utilization > 95:
            await self._create_alert(
                severity=AlertSeverity.WARNING,
                title=f"High GPU utilization on {node_id}",
                message=f"GPU utilization is {status.gpu_utilization:.1f}%",
                source=f"node:{node_id}",
                metadata={
                    "node_id": node_id,
                    "gpu_utilization": status.gpu_utilization,
                },
            )
        
        # Check for high temperature
        if status.temperature and status.temperature > 85:
            await self._create_alert(
                severity=AlertSeverity.CRITICAL,
                title=f"High temperature on {node_id}",
                message=f"Temperature is {status.temperature:.1f}°C",
                source=f"node:{node_id}",
                metadata={
                    "node_id": node_id,
                    "temperature": status.temperature,
                },
            )

    async def create_custom_alert(
        self,
        severity: AlertSeverity,
        title: str,
        message: str,
        source: str,
        metadata: Optional[Dict] = None,
    ) -> None:
        """Create a custom alert."""
        await self._create_alert(severity, title, message, source, metadata)

    def get_alerts(
        self,
        severity: Optional[AlertSeverity] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Alert]:
        """Get alerts, optionally filtered."""
        alerts = self._alerts
        
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        
        if since:
            alerts = [a for a in alerts if a.timestamp >= since]
        
        # Return most recent first
        alerts.sort(key=lambda a: a.timestamp, reverse=True)
        
        return alerts[:limit]

    async def _create_alert(
        self,
        severity: AlertSeverity,
        title: str,
        message: str,
        source: str,
        metadata: Optional[Dict] = None,
    ) -> None:
        """Create and process an alert."""
        import uuid
        
        alert = Alert(
            id=str(uuid.uuid4()),
            severity=severity,
            title=title,
            message=message,
            source=source,
            timestamp=datetime.utcnow(),
            metadata=metadata,
        )
        
        # Store alert
        self._alerts.append(alert)
        
        # Keep only last 1000 alerts
        if len(self._alerts) > 1000:
            self._alerts = self._alerts[-1000:]
        
        # Notify handlers
        for handler in self._alert_handlers:
            try:
                # Run handlers asynchronously
                asyncio.create_task(self._run_handler(handler, alert))
            except Exception as e:
                print(f"Alert handler failed: {e}")

    async def _run_handler(self, handler: Callable[[Alert], None], alert: Alert) -> None:
        """Run an alert handler safely."""
        try:
            handler(alert)
        except Exception as e:
            print(f"Alert handler error: {e}")


# Built-in alert handlers
def console_alert_handler(alert: Alert) -> None:
    """Print alerts to console."""
    from rich.console import Console
    
    console = Console()
    
    colors = {
        AlertSeverity.INFO: "blue",
        AlertSeverity.WARNING: "yellow",
        AlertSeverity.ERROR: "red",
        AlertSeverity.CRITICAL: "bold red",
    }
    
    color = colors.get(alert.severity, "white")
    console.print(f"[{color}]⚠ {alert.title}[/{color}]")
    console.print(f"  {alert.message}")
    console.print(f"  Source: {alert.source} at {alert.timestamp}")
    console.print()


def log_alert_handler(alert: Alert) -> None:
    """Log alerts to file."""
    import logging
    
    logger = logging.getLogger("distributed_grid.alerts")
    
    level_map = {
        AlertSeverity.INFO: logging.INFO,
        AlertSeverity.WARNING: logging.WARNING,
        AlertSeverity.ERROR: logging.ERROR,
        AlertSeverity.CRITICAL: logging.CRITICAL,
    }
    
    logger.log(
        level_map.get(alert.severity, logging.INFO),
        f"Alert: {alert.title} - {alert.message}",
        extra={
            "alert_id": alert.id,
            "source": alert.source,
            "severity": alert.severity.value,
            "metadata": alert.metadata,
        },
    )
