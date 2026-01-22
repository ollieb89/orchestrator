"""Distributed Grid - Main entry point."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console

from distributed_grid.cli import app as cli_app
from distributed_grid.config import Settings
from distributed_grid.core.orchestrator import GridOrchestrator
from distributed_grid.utils.logging import setup_logging

console = Console()
settings = Settings()


def main() -> None:
    """Main entry point for the distributed grid application."""
    setup_logging(settings.logging.level)
    
    # For now, delegate to the CLI app
    cli_app()


if __name__ == "__main__":
    main()
