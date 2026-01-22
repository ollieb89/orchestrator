"""Cluster provisioning functionality for Distributed Grid."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Dict, List

import structlog
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from distributed_grid.config import ClusterConfig
from distributed_grid.core.ssh_manager import SSHManager, SSHCommandResult

logger = structlog.get_logger(__name__)
console = Console()


class GridProvisioner:
    """Provisions cluster nodes with required environments."""
    
    def __init__(self, cluster_config: ClusterConfig) -> None:
        self.cluster_config = cluster_config
        self.ssh_manager = SSHManager(cluster_config.nodes)
        
        # Default packages to install
        self.default_pip_packages = [
            "torch",
            "tensorflow", 
            "numpy",
            "pandas",
            "black",
            "pylint",
            "pytest",
            "jupyter"
        ]
        
        self.default_npm_packages = [
            "typescript",
            "nodemon",
            "yarn"
        ]
    
    async def provision_all(
        self,
        pip_packages: List[str] | None = None,
        npm_packages: List[str] | None = None,
        python_version: str = "3.11",
        workspace_root: str = "~/grid_workspace"
    ) -> None:
        """Provision all nodes in the cluster."""
        pip_packages = pip_packages or self.default_pip_packages
        npm_packages = npm_packages or self.default_npm_packages
        
        console.print("[blue]Starting cluster provisioning...[/blue]")
        
        await self.ssh_manager.initialize()
        
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                
                for node in self.cluster_config.nodes:
                    task = progress.add_task(
                        f"Provisioning {node.name} ({node.host})...",
                        total=None
                    )
                    
                    await self._provision_node(
                        node,
                        pip_packages,
                        npm_packages,
                        python_version,
                        workspace_root
                    )
                    
                    progress.update(task, completed=True)
                    console.print(f"[green]✓[/green] {node.name} provisioned successfully")
            
            console.print("[green]✓[/green] All nodes provisioned successfully")
            
        except Exception as e:
            console.print(f"[red]✗[/red] Provisioning failed: {e}")
            raise
        finally:
            await self.ssh_manager.close_all()
    
    async def _provision_node(
        self,
        node,
        pip_packages: List[str],
        npm_packages: List[str],
        python_version: str,
        workspace_root: str
    ) -> None:
        """Provision a single node."""
        logger.info("Provisioning node", node=node.name)
        
        # 1. Create workspace directory
        await self.ssh_manager.run_command(
            node.name,
            f"mkdir -p {workspace_root}",
            timeout=30
        )
        
        # 2. Create Python virtual environment
        venv_path = f"{workspace_root}/grid_env"
        await self.ssh_manager.run_command(
            node.name,
            f"python{python_version} -m venv {venv_path}",
            timeout=60
        )
        
        # 3. Upgrade pip and install Python packages
        pip_bin = f"{venv_path}/bin/pip"
        pip_list = " ".join(pip_packages)
        
        await self.ssh_manager.run_command(
            node.name,
            f"{pip_bin} install -U pip {pip_list}",
            timeout=300  # 5 minutes for package installation
        )
        
        # 4. Setup npm global packages (if node/npm is available)
        npm_check = await self.ssh_manager.run_command(
            node.name,
            "which npm",
            timeout=10
        )
        
        if npm_check.exit_status == 0:
            # Configure npm to use user-local prefix
            await self.ssh_manager.run_command(
                node.name,
                "mkdir -p ~/.npm-global && npm config set prefix '~/.npm-global'",
                timeout=30
            )
            
            # Install npm packages
            npm_list = " ".join(npm_packages)
            await self.ssh_manager.run_command(
                node.name,
                f"export PATH=~/.npm-global/bin:$PATH && npm install -g {npm_list}",
                timeout=180
            )
        else:
            logger.info("npm not found on node, skipping npm packages", node=node.name)
        
        # 5. Create activation script
        activation_script = f"""
# Grid Environment Activation Script
export PATH="{venv_path}/bin:$PATH"
export PATH="$HOME/.npm-global/bin:$PATH"
export GRID_WORKSPACE="{workspace_root}"
echo "Grid environment activated. Workspace: {workspace_root}"
"""
        
        await self.ssh_manager.run_command(
            node.name,
            f"cat > {workspace_root}/activate_grid.sh << 'EOF'\n{activation_script}\nEOF",
            timeout=30
        )
        
        await self.ssh_manager.run_command(
            node.name,
            f"chmod +x {workspace_root}/activate_grid.sh",
            timeout=10
        )
    
    async def check_node_status(self, node_name: str) -> Dict[str, bool]:
        """Check provisioning status of a node."""
        node = self.cluster_config.get_node_by_name(node_name)
        if not node:
            raise ValueError(f"Node {node_name} not found in configuration")
        
        await self.ssh_manager.initialize()
        
        try:
            workspace_root = "~/grid_workspace"
            venv_path = f"{workspace_root}/grid_env"
            
            checks = {}
            
            # Check workspace exists
            result = await self.ssh_manager.run_command(
                node.name,
                f"test -d {workspace_root}",
                timeout=10
            )
            checks["workspace"] = result.exit_status == 0
            
            # Check venv exists
            result = await self.ssh_manager.run_command(
                node.name,
                f"test -d {venv_path}",
                timeout=10
            )
            checks["venv"] = result.exit_status == 0
            
            # Check pip is accessible
            result = await self.ssh_manager.run_command(
                node.name,
                f"{venv_path}/bin/pip --version",
                timeout=10
            )
            checks["pip"] = result.exit_status == 0
            
            # Check activation script exists
            result = await self.ssh_manager.run_command(
                node.name,
                f"test -f {workspace_root}/activate_grid.sh",
                timeout=10
            )
            checks["activation_script"] = result.exit_status == 0
            
            return checks
            
        finally:
            await self.ssh_manager.close_all()
