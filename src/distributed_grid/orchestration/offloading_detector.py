"""Resource offloading detection system for identifying offloadable processes."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, asdict
from datetime import datetime, UTC
from typing import Dict, List, Optional, Tuple, Set
from enum import Enum

import structlog
from pydantic import BaseModel

from distributed_grid.core.ssh_manager import SSHManager
from distributed_grid.config import ClusterConfig, NodeConfig
from distributed_grid.orchestration.resource_sharing import ResourceType, ResourceOffer

logger = structlog.get_logger(__name__)


class ProcessType(str, Enum):
    """Types of processes that can be offloaded."""
    TRAINING = "training"
    INFERENCE = "inference"
    DATA_PROCESSING = "data_processing"
    COMPUTE_INTENSIVE = "compute_intensive"
    IO_INTENSIVE = "io_intensive"
    BATCH_JOB = "batch_job"
    INTERACTIVE = "interactive"
    DAEMON = "daemon"


@dataclass
class ProcessInfo:
    """Information about a running process."""
    pid: int
    name: str
    cmdline: List[str]
    cpu_percent: float
    memory_mb: int
    gpu_memory_mb: int = 0
    gpu_utilization: float = 0.0
    user: str = ""
    start_time: Optional[datetime] = None
    parent_pid: Optional[int] = None
    process_type: Optional[ProcessType] = None
    offloadable: bool = False
    offload_reason: str = ""
    resource_requirements: Dict[str, int] = None
    
    def __post_init__(self):
        if self.resource_requirements is None:
            self.resource_requirements = {}


@dataclass
class OffloadingRecommendation:
    """A recommendation for offloading a process to a specific node."""
    process: ProcessInfo
    source_node: str  # Add source node tracking
    target_node: str
    confidence: float  # 0.0 to 1.0
    reason: str
    resource_match: Dict[str, Tuple[int, int]]  # resource -> (required, available)
    migration_complexity: str  # "low", "medium", "high"


class ProcessClassifier:
    """Classifies processes based on their characteristics."""
    
    # Patterns to identify different process types
    PATTERNS = {
        ProcessType.TRAINING: [
            r"python.*train",
            r"python.*model.*train",
            r"tensorflow",
            r"pytorch",
            r"torch\.",
            r"keras",
            r"fit\s*\(.*model",
            r"model\.fit",
            r"trainer",
            r"accelerate\slaunch",
            r"deepspeed",
        ],
        ProcessType.INFERENCE: [
            r"python.*infer",
            r"python.*predict",
            r"python.*serve",
            r"uvicorn",
            r"gunicorn",
            r"fastapi",
            r"flask",
            r"streamlit",
            r"gradio",
            r"transformers.*pipeline",
        ],
        ProcessType.DATA_PROCESSING: [
            r"pandas",
            r"numpy",
            r"scipy",
            r"dask",
            r"spark",
            r" airflow",
            r"prefect",
            r"luigi",
            r"etl",
        ],
        ProcessType.COMPUTE_INTENSIVE: [
            r"numpy",
            r"scipy",
            r"sklearn",
            r"jax",
            r"xgboost",
            r"lightgbm",
            r"catboost",
        ],
        ProcessType.IO_INTENSIVE: [
            r"rsync",
            r"scp",
            r"wget",
            r"curl",
            r"tar",
            r"zip",
            r"unzip",
            r"dd",
        ],
        ProcessType.BATCH_JOB: [
            r"bash.*\.sh",
            r"sh.*\.sh",
            r"cron",
            r"atd",
            r"batch",
        ],
        ProcessType.DAEMON: [
            r"systemd",
            r"init",
            r"cron",
            r"rsyslog",
            r"dockerd",
            r"containerd",
            r"kubelet",
        ],
        ProcessType.INTERACTIVE: [
            r"python.*ipython",
            r"python.*jupyter",
            r"bash",
            r"zsh",
            r"tmux",
            r"screen",
            r"vim",
            r"nano",
            r"windsurf",
            r"chrome",
            r"code",
        ],
    }
    
    @classmethod
    def classify_process(cls, process: ProcessInfo) -> Optional[ProcessType]:
        """Classify a process based on its command line."""
        cmdline_str = " ".join(process.cmdline).lower()
        
        for process_type, patterns in cls.PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, cmdline_str, re.IGNORECASE):
                    return process_type
        
        # Heuristic classification based on resource usage
        if process.gpu_memory_mb > 0 or process.gpu_utilization > 0:
            return ProcessType.COMPUTE_INTENSIVE
        
        if process.cpu_percent > 80:
            return ProcessType.COMPUTE_INTENSIVE
        
        if process.memory_mb > 1024:  # > 1GB (Lowered from 8GB)
            return ProcessType.DATA_PROCESSING
        
        return None


class OffloadingDetector:
    """Detects processes that can be offloaded to other nodes."""
    
    def __init__(
        self,
        ssh_manager: SSHManager,
        cluster_config: ClusterConfig,
        detection_interval: int = 30,
    ):
        """Initialize the offloading detector."""
        self.ssh_manager = ssh_manager
        self.cluster_config = cluster_config
        self.detection_interval = detection_interval
        self.classifier = ProcessClassifier()
        
        # Process monitoring script
        self._monitor_script = self._create_monitor_script()
        
        # Cache of node capabilities
        self._node_capabilities: Dict[str, Dict] = {}
        
        # History of offloading decisions
        self._offloading_history: List[OffloadingRecommendation] = []

    async def stop(self) -> None:
        """Stop the offloading detector."""
        # No background tasks to stop currently
        pass
    
    def _create_monitor_script(self) -> str:
        """Create the process monitoring script."""
        return '''import json
import psutil
import subprocess
import time
from datetime import datetime, timezone

def get_gpu_processes():
    """Get processes using GPU."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", 
             "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            gpu_procs = {}
            for line in result.stdout.strip().split("\\n") if result.stdout.strip() else []:
                parts = line.split(", ")
                if len(parts) >= 3:
                    pid = int(parts[0])
                    name = parts[1]
                    memory_mb = int(parts[2])
                    gpu_procs[pid] = {"name": name, "memory_mb": memory_mb}
            return gpu_procs
    except Exception:
        pass
    return {}

def get_process_info():
    """Get information about all running processes."""
    gpu_processes = get_gpu_processes()
    processes = []
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cpu_percent', 
                                   'memory_info', 'username', 'create_time', 'ppid']):
        try:
            pinfo = proc.info
            
            # Get GPU info if available
            gpu_info = gpu_processes.get(pinfo['pid'], {})
            
            process = {
                "pid": pinfo['pid'],
                "name": pinfo['name'] or "",
                "cmdline": pinfo['cmdline'] or [],
                "cpu_percent": pinfo['cpu_percent'] or 0.0,
                "memory_mb": (pinfo['memory_info'].rss / (1024*1024)) if pinfo['memory_info'] else 0,
                "gpu_memory_mb": gpu_info.get("memory_mb", 0),
                "user": pinfo['username'] or "",
                "start_time": datetime.fromtimestamp(pinfo['create_time'], tz=timezone.utc).isoformat() if pinfo['create_time'] else None,
                "parent_pid": pinfo['ppid'],
            }
            processes.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "processes": processes
    }

if __name__ == "__main__":
    print(json.dumps(get_process_info(), indent=2))
'''
    
    async def discover_processes(self, node_id: str) -> List[ProcessInfo]:
        """Discover processes running on a specific node."""
        try:
            # Write script to temp file and execute
            temp_script = "/tmp/grid_process_monitor.py"
            
            # First, write the script to the remote node
            write_cmd = f"cat > {temp_script} << 'EOF'\n{self._monitor_script}\nEOF"
            await self.ssh_manager.run_command(node_id, write_cmd, timeout=5)
            
            # Execute the script
            result = await self.ssh_manager.run_command(
                node_id,
                f"python3 {temp_script}",
                timeout=10,
            )
            
            if result.exit_status != 0:
                logger.error("Failed to discover processes", node=node_id, error=result.stderr)
                return []
            
            data = json.loads(result.stdout)
            processes = []
            
            for proc_data in data["processes"]:
                # Skip system processes and very short-lived processes
                if proc_data["pid"] < 100 or proc_data["memory_mb"] < 10:
                    continue
                
                process = ProcessInfo(
                    pid=proc_data["pid"],
                    name=proc_data["name"],
                    cmdline=proc_data["cmdline"],
                    cpu_percent=proc_data["cpu_percent"],
                    memory_mb=int(proc_data["memory_mb"]),
                    gpu_memory_mb=proc_data["gpu_memory_mb"],
                    user=proc_data["user"],
                    start_time=datetime.fromisoformat(proc_data["start_time"]) if proc_data["start_time"] else None,
                    parent_pid=proc_data["parent_pid"],
                )
                
                # Classify the process
                process.process_type = self.classifier.classify_process(process)
                
                # Determine if it's offloadable
                process.offloadable, process.offload_reason = self._is_offloadable(process)
                
                # Estimate resource requirements
                process.resource_requirements = self._estimate_resource_requirements(process)
                
                processes.append(process)
            
            return processes
            
        except Exception as e:
            logger.error("Failed to discover processes", node=node_id, error=str(e))
            return []
    
    def _is_offloadable(self, process: ProcessInfo) -> Tuple[bool, str]:
        """Determine if a process can be offloaded."""
        # Skip critical system processes
        if process.pid < 100:
            return False, "System process"
        
        # Skip daemons and services
        if process.process_type == ProcessType.DAEMON:
            return False, "Daemon/service process"
        
        # Determine if it's a memory-intensive interactive process
        # We previously skipped all interactive processes, but now we allow them if memory-hungry
        is_memory_intensive = process.memory_mb > 1024  # > 1GB
        
        if process.process_type == ProcessType.INTERACTIVE and not is_memory_intensive:
            return False, "Interactive process (not memory intensive enough)"
        
        # Skip processes with very low resource usage
        if not is_memory_intensive and process.cpu_percent < 5 and process.gpu_memory_mb == 0:
            return False, "Insufficient resource usage"
        
        # Check if process is long-running
        if process.start_time:
            runtime = datetime.now(UTC) - process.start_time.replace(tzinfo=UTC)
            if runtime.total_seconds() < 60:  # Less than 1 minute
                return False, "Process too new"
        
        # GPU processes are good candidates
        if process.gpu_memory_mb > 0:
            return True, "GPU-intensive process"
        
        # Memory-intensive processes
        if is_memory_intensive:
            return True, f"Memory-intensive process ({process.memory_mb}MB)"
        
        # CPU-intensive processes
        if process.cpu_percent > 50:
            return True, "CPU-intensive process"
        
        # Training and inference processes
        if process.process_type in [ProcessType.TRAINING, ProcessType.INFERENCE]:
            return True, f"{process.process_type.value} process"
        
        return False, "Not resource-intensive enough"
    
    def _estimate_resource_requirements(self, process: ProcessInfo) -> Dict[str, int]:
        """Estimate the resource requirements for a process."""
        requirements = {}
        
        # CPU requirements (add some buffer)
        if process.cpu_percent > 0:
            requirements["cpu"] = max(1, int(process.cpu_percent / 20))
        
        # Memory requirements (add 25% buffer)
        if process.memory_mb > 0:
            requirements["memory_gb"] = max(1, int(process.memory_mb * 1.25 / 1024))
        
        # GPU requirements
        if process.gpu_memory_mb > 0:
            requirements["gpu"] = 1
            # Estimate GPU memory requirement with buffer
            requirements["gpu_memory_gb"] = max(1, int(process.gpu_memory_mb * 1.5 / 1024))
        
        return requirements
    
    async def detect_offloading_candidates(
        self,
        target_node: Optional[str] = None,
    ) -> List[OffloadingRecommendation]:
        """Find processes that can be offloaded to other nodes."""
        recommendations = []
        
        # Identify master node (where command is run from)
        master_node = None
        for node in self.cluster_config.nodes:
            if "master" in node.tags:
                master_node = node.name
                break
        
        # If no master tag found, assume first node is master
        if not master_node:
            master_node = self.cluster_config.nodes[0].name
        
        # Only scan the master node for processes to offload
        nodes_to_scan = [master_node]
        
        # Discover processes on master node
        all_processes = {}
        for node_id in nodes_to_scan:
            try:
                processes = await self.discover_processes(node_id)
                all_processes[node_id] = [p for p in processes if p.offloadable]
            except Exception as e:
                logger.error("Failed to get processes", node=node_id, error=str(e))
                all_processes[node_id] = []
        
        # Get node capabilities
        await self._update_node_capabilities()
        
        # Find offloading opportunities from master to workers
        for source_node, processes in all_processes.items():
            for process in processes:
                # Find suitable target nodes (only workers, not master)
                suitable_targets = await self._find_suitable_targets(process, source_node, exclude_master=True)
                
                # Filter by target node if specified
                if target_node:
                    suitable_targets = [t for t in suitable_targets if t[0] == target_node]
                
                for target_node, match_info in suitable_targets:
                    recommendation = OffloadingRecommendation(
                        process=process,
                        source_node=source_node,
                        target_node=target_node,
                        confidence=self._calculate_confidence(process, match_info),
                        reason=self._generate_reason(process, match_info),
                        resource_match=match_info,
                        migration_complexity=self._assess_migration_complexity(process),
                    )
                    recommendations.append(recommendation)
        
        # Sort by confidence
        recommendations.sort(key=lambda r: r.confidence, reverse=True)
        
        # Group by PID and keep only the best recommendation for each process
        best_recommendations = {}
        for rec in recommendations:
            pid = rec.process.pid
            if pid not in best_recommendations or rec.confidence > best_recommendations[pid].confidence:
                best_recommendations[pid] = rec
        
        return list(best_recommendations.values())
    
    async def _update_node_capabilities(self) -> None:
        """Update cached node capabilities."""
        for node in self.cluster_config.nodes:
            self._node_capabilities[node.name] = {
                "cpu_cores": node.gpu_count * 4,  # Estimate
                "memory_gb": node.memory_gb,
                "gpu_count": node.gpu_count,
                "gpu_memory_gb": 8,  # Estimate, should be detected dynamically
            }
    
    async def _find_suitable_targets(
        self,
        process: ProcessInfo,
        source_node: str,
        exclude_master: bool = False,
    ) -> List[Tuple[str, Dict[str, Tuple[int, int]]]]:
        """Find suitable target nodes for a process."""
        suitable = []
        
        for target_node, capabilities in self._node_capabilities.items():
            if target_node == source_node:
                continue
            
            # Skip master node if exclude_master is True
            if exclude_master:
                target_node_config = None
                for node in self.cluster_config.nodes:
                    if node.name == target_node:
                        target_node_config = node
                        break
                if target_node_config and "master" in target_node_config.tags:
                    continue
            
            # Check resource availability
            match_info = {}
            suitable_node = True
            
            for resource, required in process.resource_requirements.items():
                available = capabilities.get(resource, 0)
                
                if resource == "cpu" and available >= required:
                    match_info[resource] = (required, available)
                elif resource == "memory_gb" and available >= required:
                    match_info[resource] = (required, available)
                elif resource == "gpu" and available >= required:
                    match_info[resource] = (required, available)
                elif resource == "gpu_memory_gb" and capabilities.get("gpu_memory_gb", 0) >= required:
                    match_info[resource] = (required, capabilities.get("gpu_memory_gb", 0))
                else:
                    suitable_node = False
                    break
            
            if suitable_node and match_info:
                suitable.append((target_node, match_info))
        
        return suitable
    
    def _calculate_confidence(
        self,
        process: ProcessInfo,
        match_info: Dict[str, Tuple[int, int]],
    ) -> float:
        """Calculate confidence score for offloading."""
        confidence = 0.5  # Base confidence
        
        # Higher confidence for GPU processes
        if process.gpu_memory_mb > 0:
            confidence += 0.3
        
        # Higher confidence for long-running processes
        if process.start_time:
            runtime = datetime.now(UTC) - process.start_time.replace(tzinfo=UTC)
            if runtime.total_seconds() > 3600:  # > 1 hour
                confidence += 0.2
        
        # Adjust based on resource match quality
        for resource, (required, available) in match_info.items():
            ratio = required / available if available > 0 else 1.0
            if ratio < 0.5:  # Process uses less than 50% of available
                confidence += 0.1
            elif ratio > 0.8:  # Process uses most of available
                confidence -= 0.1
        
        return min(1.0, max(0.0, confidence))
    
    def _generate_reason(
        self,
        process: ProcessInfo,
        match_info: Dict[str, Tuple[int, int]],
    ) -> str:
        """Generate a reason for the offloading recommendation."""
        reasons = []
        
        if process.process_type:
            reasons.append(f"{process.process_type.value} process")
        
        if process.gpu_memory_mb > 0:
            reasons.append(f"using {process.gpu_memory_mb}MB GPU memory")
        
        if process.cpu_percent > 50:
            reasons.append(f"high CPU usage ({process.cpu_percent:.1f}%)")
        
        if process.memory_mb > 2048:
            reasons.append(f"high memory usage ({process.memory_mb}MB)")
        
        # Add resource availability info with proper formatting
        resource_strs = []
        for resource, (required, available) in match_info.items():
            if resource == "memory_gb":
                resource_strs.append(f"{required}GB/{available}GB memory")
            elif resource == "gpu_memory_gb":
                resource_strs.append(f"{required}GB/{available}GB GPU memory")
            elif resource == "cpu":
                resource_strs.append(f"{required}/{available} CPU cores")
            elif resource == "gpu":
                resource_strs.append(f"{required}/{available} GPUs")
            else:
                resource_strs.append(f"{required}/{available} {resource}")
        
        if resource_strs:
            reasons.append(f"target has {', '.join(resource_strs)} available")
        
        return "; ".join(reasons)
    
    def _assess_migration_complexity(self, process: ProcessInfo) -> str:
        """Assess the complexity of migrating a process."""
        # High complexity for GPU processes
        if process.gpu_memory_mb > 0:
            return "high"
        
        # Medium complexity for processes with state
        if process.process_type in [ProcessType.TRAINING, ProcessType.INFERENCE]:
            return "medium"
        
        # Low complexity for batch jobs
        if process.process_type == ProcessType.BATCH_JOB:
            return "low"
        
        # Default to medium
        return "medium"
    
    async def get_offloadable_processes_summary(self) -> Dict:
        """Get a summary of offloadable processes across the cluster."""
        recommendations = await self.find_offloading_opportunities()
        
        summary = {
            "timestamp": datetime.now(UTC).isoformat(),
            "total_offloadable": len(recommendations),
            "by_source_node": {},
            "by_target_node": {},
            "by_process_type": {},
            "high_confidence": [],
        }
        
        for rec in recommendations:
            # Group by source node
            source = rec.source_node or "unknown"
            summary["by_source_node"][source] = summary["by_source_node"].get(source, 0) + 1
            
            # Group by target node
            summary["by_target_node"][rec.target_node] = summary["by_target_node"].get(rec.target_node, 0) + 1
            
            # Group by process type
            proc_type = rec.process.process_type or "unknown"
            summary["by_process_type"][proc_type] = summary["by_process_type"].get(proc_type, 0) + 1
            
            # High confidence recommendations
            if rec.confidence > 0.7:
                summary["high_confidence"].append({
                    "pid": rec.process.pid,
                    "name": rec.process.name,
                    "target": rec.target_node,
                    "confidence": rec.confidence,
                    "reason": rec.reason,
                })
        
        return summary
