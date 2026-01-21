import click
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import ClusterConfig
from cluster.manager_optimized import OptimizedClusterManager
from cluster.executor_optimized import OptimizedExecutor
from utils.logging import setup_logging

@click.group()
@click.option('--log-level', default='INFO', help='Logging level')
@click.pass_context
def cli(ctx, log_level):
    """Grid Cluster Manager CLI"""
    ctx.ensure_object(dict)
    setup_logging(log_level)

@cli.command()
@click.argument('action', type=click.Choice(['install', 'start', 'stop', 'status']))
def cluster(action):
    """Manage cluster lifecycle"""
    manager = OptimizedClusterManager()
    
    if action == 'install':
        manager.install()
    elif action == 'start':
        manager.start()
    elif action == 'stop':
        manager.stop()
    elif action == 'status':
        manager.status()

@cli.command()
@click.argument('command', nargs=-1, required=True)
@click.option('-p', '--port', type=int, help='Port to forward')
def run(command, port):
    """Execute command on best node"""
    executor = OptimizedExecutor()
    result = executor.run_distributed(' '.join(command))
    click.echo(result)

@cli.command()
def health():
    """Check cluster health"""
    from core.health_check import HealthChecker
    config = ClusterConfig.from_yaml(
        str(Path(__file__).parent.parent / "config" / "cluster_config.yaml")
    )
    
    checker = HealthChecker()
    healths = checker.check_all_nodes(config.nodes)
    
    click.echo("Cluster Health Status:")
    click.echo("-" * 60)
    
    for health in healths:
        status = "✓ HEALTHY" if health.is_healthy else "✗ UNHEALTHY"
        click.echo(
            f"{health.host:<20} {status:<15} "
            f"CPU: {health.cpu_load:>6.2f}  GPU: {health.gpu_memory_percent:>6.1f}%  "
            f"Score: {health.score:>6.1f}"
        )

@cli.command()
def metrics():
    """Export Prometheus metrics"""
    from utils.metrics import get_metrics
    metrics = get_metrics()
    click.echo(metrics.export_prometheus())

if __name__ == '__main__':
    cli(obj={})
