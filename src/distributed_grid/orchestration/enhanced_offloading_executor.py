"""Enhanced process offloading executor with intelligent resource sharing."""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, UTC, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Callable
from enum import Enum
import math

import ray
import structlog
from ray.dashboard.modules.job.sdk import JobSubmissionClient
from ray.dashboard.modules.job.common import JobStatus

from distributed_grid.core.ssh_manager import SSHManager
from distributed_grid.config import ClusterConfig, NodeConfig
from distributed_grid.orchestration.offloading_detector import (
    ProcessInfo,
    OffloadingRecommendation,
    ProcessType,
)
from distributed_grid.monitoring.resource_metrics import ResourceMetricsCollector, ResourceType
from distributed_grid.orchestration.resource_sharing_manager import (
    ResourceSharingManager,
    AllocationPriority,
)
from distributed_grid.orchestration.intelligent_scheduler import (
    IntelligentScheduler,
    SchedulingRequest,
    ResourceRequirement,
    SchedulingStrategy,
    TaskPriority,
)
from distributed_grid.orchestration.resource_boost_manager import (
    ResourceBoostManager,
)

logger = structlog.get_logger(__name__)


class OffloadingMode(str, Enum):
    """Offloading modes for resource utilization."""
    OFFLOAD_ONLY = "offload_only"  # Original offloading behavior
    SHARE_AND_OFFLOAD = "share_and_offload"  # Use shared resources first
    DYNAMIC_BALANCING = "dynamic_balancing"  # Dynamically decide based on cluster state


@dataclass
class ResourceAnalysis:
    """Analysis of resource requirements for a process."""
    process_info: ProcessInfo
    cpu_requirement: float
    memory_requirement_mb: int
    gpu_requirement: int
    estimated_duration: Optional[timedelta] = None
    priority: TaskPriority = TaskPriority.NORMAL
    can_share_resources: bool = True
    
    def to_resource_requirement(self) -> ResourceRequirement:
        """Convert to ResourceRequirement for scheduler."""
        return ResourceRequirement(
            cpu_count=self.cpu_requirement,
            memory_mb=self.memory_requirement_mb,
            gpu_count=self.gpu_requirement,
        )


@dataclass
class OffloadingDecision:
    """Decision on how to handle process offloading."""
    mode: OffloadingMode
    target_node: Optional[str] = None
    use_shared_resources: bool = False
    resource_allocation_id: Optional[str] = None
    placement_group: Optional[Any] = None
    reasoning: List[str] = field(default_factory=list)
    confidence: float = 0.0


class EnhancedOffloadingExecutor:
    """Enhanced offloading executor with intelligent resource sharing."""
    
    def __init__(
        self,
        ssh_manager: SSHManager,
        cluster_config: ClusterConfig,
        ray_dashboard_address: str = "http://localhost:8265",
        mode: OffloadingMode = OffloadingMode.DYNAMIC_BALANCING,
        metrics_collector: Optional[ResourceMetricsCollector] = None,
        resource_sharing_manager: Optional[ResourceSharingManager] = None,
        intelligent_scheduler: Optional[IntelligentScheduler] = None,
        boost_manager: Optional[ResourceBoostManager] = None,
    ):
        """Initialize the enhanced offloading executor."""
        self.ssh_manager = ssh_manager
        self.cluster_config = cluster_config
        self.ray_dashboard_address = ray_dashboard_address
        self.mode = mode
        
        # Resource management components
        self.metrics_collector = metrics_collector
        self.resource_sharing_manager = resource_sharing_manager
        self.intelligent_scheduler = intelligent_scheduler
        self.boost_manager = boost_manager
        
        # Active tasks and history
        self._active_tasks: Dict[str, Dict[str, Any]] = {}
        self._task_history: List[Dict[str, Any]] = []
        self._monitoring_tasks: Dict[str, asyncio.Task] = {}
        
        # Ray job client
        self._job_client: Optional[JobSubmissionClient] = None
        
        # Performance metrics
        self._performance_metrics: Dict[str, Dict[str, float]] = {}
        
    async def initialize(self) -> None:
        """Initialize the executor and all components."""
        # Initialize Ray job client
        self._job_client = JobSubmissionClient(self.ray_dashboard_address)
        
        # Initialize components if not provided
        if not self.metrics_collector:
            from distributed_grid.monitoring.resource_metrics import ResourceMetricsCollector
            self.metrics_collector = ResourceMetricsCollector(self.cluster_config)
            await self.metrics_collector.start()
            
        if not self.resource_sharing_manager:
            from distributed_grid.orchestration.resource_sharing_manager import ResourceSharingManager, SharingPolicy
            self.resource_sharing_manager = ResourceSharingManager(
                self.cluster_config,
                self.metrics_collector,
                policy=SharingPolicy.BALANCED,
            )
            await self.resource_sharing_manager.start()
            
        if not self.intelligent_scheduler:
            from distributed_grid.orchestration.intelligent_scheduler import IntelligentScheduler
            self.intelligent_scheduler = IntelligentScheduler(
                self.cluster_config,
                self.metrics_collector,
                self.resource_sharing_manager,
                boost_manager=self.boost_manager,
            )
            
        logger.info(
            "Enhanced offloading executor initialized",
            mode=self.mode,
            dashboard=self.ray_dashboard_address,
        )
        
    def validate_offload_target(self, recommendation: OffloadingRecommendation) -> Tuple[bool, str]:
        """Validate that the offload target is allowed.

        Returns:
            Tuple of (is_valid, reason)
        """
        head_node_id = self.cluster_config.nodes[0].name if self.cluster_config.nodes else None

        # Never allow offloading TO the head node
        if recommendation.target_node == head_node_id:
            return False, f"Cannot offload TO head node ({head_node_id})"

        return True, "Valid target"

    async def execute_offloading(
        self,
        recommendation: OffloadingRecommendation,
        capture_state: bool = True,
        runtime_env: Optional[Dict] = None,
    ) -> str:
        """Execute offloading with intelligent resource sharing."""
        # Validate target first
        is_valid, reason = self.validate_offload_target(recommendation)
        if not is_valid:
            raise ValueError(reason)

        task_id = f"enhanced_offload_{int(time.time())}_{recommendation.process.pid}"
        
        # Analyze resource requirements
        resource_analysis = await self._analyze_process_requirements(recommendation.process)
        
        # Make offloading decision
        decision = await self._make_offloading_decision(recommendation, resource_analysis)
        
        # Store task info
        self._active_tasks[task_id] = {
            "recommendation": recommendation,
            "resource_analysis": resource_analysis,
            "decision": decision,
            "status": "pending",
            "created_at": datetime.now(UTC),
        }
        
        logger.info(
            "Starting enhanced offloading",
            task_id=task_id,
            mode=decision.mode,
            target=decision.target_node,
            use_shared=decision.use_shared_resources,
        )
        
        try:
            # Execute based on decision
            if decision.mode == OffloadingMode.SHARE_AND_OFFLOAD and decision.use_shared_resources:
                result = await self._execute_with_shared_resources(task_id, decision, runtime_env)
            elif decision.mode == OffloadingMode.DYNAMIC_BALANCING:
                result = await self._execute_dynamic_balancing(task_id, decision, runtime_env)
            else:
                # Fall back to original offloading
                result = await self._execute_original_offloading(task_id, recommendation, runtime_env)
                
            # Update task status
            self._active_tasks[task_id]["status"] = "running"
            self._active_tasks[task_id]["started_at"] = datetime.now(UTC)
            
            # Start monitoring
            monitor_task = asyncio.create_task(self._monitor_task(task_id, result))
            self._monitoring_tasks[task_id] = monitor_task
            
            return task_id
            
        except Exception as e:
            self._active_tasks[task_id]["status"] = "failed"
            self._active_tasks[task_id]["error"] = str(e)
            logger.error("Enhanced offloading failed", task_id=task_id, error=str(e))
            raise
            
    async def _analyze_process_requirements(self, process: ProcessInfo) -> ResourceAnalysis:
        """Analyze resource requirements for a process."""
        # Base requirements from process info
        cpu_req = max(1.0, process.cpu_percent / 100.0 * 4)  # Scale up CPU requirement
        memory_req = max(1024, process.memory_mb)  # At least 1GB
        gpu_req = 1 if process.gpu_memory_mb > 0 else 0
        
        # Adjust based on process type
        if process.process_type == ProcessType.TRAINING:
            cpu_req *= 2
            memory_req *= 2
            gpu_req = max(gpu_req, 1)
        elif process.process_type == ProcessType.DATA_PROCESSING:
            cpu_req *= 1.5
            memory_req *= 1.5
        elif process.process_type == ProcessType.INFERENCE:
            gpu_req = max(gpu_req, 1)
            memory_req = max(memory_req, 2048)  # At least 2GB for inference
            
        # Estimate duration based on process age and type
        age_seconds = 0.0
        if process.start_time:
            age_seconds = (datetime.now(UTC) - process.start_time).total_seconds()
        if age_seconds > 0:
            # Long-running processes likely need more resources
            if age_seconds > 300:  # 5 minutes
                memory_req *= 1.5
                
        # Determine priority
        priority = TaskPriority.NORMAL
        if process.process_type in [ProcessType.TRAINING, ProcessType.COMPUTE_INTENSIVE]:
            priority = TaskPriority.HIGH
            
        return ResourceAnalysis(
            process_info=process,
            cpu_requirement=cpu_req,
            memory_requirement_mb=memory_req,
            gpu_requirement=gpu_req,
            priority=priority,
            can_share_resources=gpu_req == 0 or process.process_type != ProcessType.TRAINING,
        )
        
    async def _make_offloading_decision(
        self,
        recommendation: OffloadingRecommendation,
        analysis: ResourceAnalysis,
    ) -> OffloadingDecision:
        """Make an intelligent offloading decision."""
        decision = OffloadingDecision(mode=self.mode)
        
        # Get current cluster state
        snapshots = self.metrics_collector.get_all_latest_snapshots()
        cluster_summary = self.metrics_collector.get_cluster_summary()
        
        # Check for active boosts on master node
        master_has_active_boosts = False
        boosted_resources = {"cpu": 0.0, "memory": 0.0, "gpu": 0.0}
        
        if self.boost_manager:
            try:
                active_boosts = await self.boost_manager.get_active_boosts(target_node="gpu-master")
                if active_boosts:
                    master_has_active_boosts = True
                    # Aggregate boosted resources
                    for boost in active_boosts:
                        if boost.resource_type.value.lower() == "cpu":
                            boosted_resources["cpu"] += boost.amount
                        elif boost.resource_type.value.lower() == "memory":
                            boosted_resources["memory"] += boost.amount  # Already in GB
                        elif boost.resource_type.value.lower() == "gpu":
                            boosted_resources["gpu"] += boost.amount
                    decision.reasoning.append(
                        f"Active boosts detected on master: "
                        f"CPU={boosted_resources['cpu']:.1f}, "
                        f"Memory={boosted_resources['memory']:.1f}GB, "
                        f"GPU={boosted_resources['gpu']:.0f}"
                    )
            except Exception as e:
                logger.warning(f"Failed to check active boosts: {e}")
        
        # Check if master has resources (including boosted resources)
        master_snapshot = snapshots.get("gpu-master")
        master_has_resources = False
        
        if master_snapshot:
            # Calculate available resources including boosts
            cpu_available = master_snapshot.cpu_available + boosted_resources["cpu"]
            memory_available = master_snapshot.memory_available + (boosted_resources["memory"] * 1024 * 1024 * 1024)
            gpu_available = master_snapshot.gpu_available + boosted_resources["gpu"]
            
            master_has_resources = (
                cpu_available >= analysis.cpu_requirement and
                memory_available >= analysis.memory_requirement_mb * 1024 * 1024 and
                gpu_available >= analysis.gpu_requirement
            )
        memory_pressure_offload = await self._should_offload_for_memory(
            "gpu-master",
            analysis.memory_requirement_mb / 1024,
        )
            
        # Decision logic based on mode
        if self.mode == OffloadingMode.OFFLOAD_ONLY:
            decision.mode = OffloadingMode.OFFLOAD_ONLY
            decision.target_node = recommendation.target_node
            decision.reasoning.append("Using original offloading mode")
            
        elif self.mode == OffloadingMode.SHARE_AND_OFFLOAD:
            if master_has_resources and analysis.can_share_resources:
                decision.mode = OffloadingMode.SHARE_AND_OFFLOAD
                decision.target_node = "gpu-master"
                decision.use_shared_resources = True
                if master_has_active_boosts:
                    decision.reasoning.append("Master has boosted resources available, using boosted resources")
                else:
                    decision.reasoning.append("Master has available resources, using shared resources")
            else:
                decision.mode = OffloadingMode.OFFLOAD_ONLY
                decision.target_node = recommendation.target_node
                decision.reasoning.append("Master lacks resources, offloading to worker")
                
        elif self.mode == OffloadingMode.DYNAMIC_BALANCING:
            # Analyze cluster pressure
            avg_pressure = cluster_summary.get("node_pressure_scores", {})
            overall_pressure = sum(avg_pressure.values()) / len(avg_pressure) if avg_pressure else 0

            if memory_pressure_offload:
                decision.mode = OffloadingMode.OFFLOAD_ONLY
                decision.target_node = recommendation.target_node
                decision.reasoning.append("Memory pressure high, offloading to worker")
            elif master_has_resources and overall_pressure < 0.7:
                # Cluster not under pressure, use master resources
                decision.mode = OffloadingMode.SHARE_AND_OFFLOAD
                decision.target_node = "gpu-master"
                decision.use_shared_resources = True
                if master_has_active_boosts:
                    decision.reasoning.append(f"Cluster pressure low ({overall_pressure:.2f}), using master boosted resources")
                else:
                    decision.reasoning.append(f"Cluster pressure low ({overall_pressure:.2f}), using master resources")
            elif analysis.can_share_resources and overall_pressure < 0.9:
                # Try to request shared resources
                decision.mode = OffloadingMode.DYNAMIC_BALANCING
                decision.target_node = "gpu-master"
                decision.use_shared_resources = True
                decision.reasoning.append(f"Requesting shared resources (pressure: {overall_pressure:.2f})")
            else:
                # High pressure, offload to worker
                decision.mode = OffloadingMode.OFFLOAD_ONLY
                decision.target_node = recommendation.target_node
                decision.reasoning.append(f"High cluster pressure ({overall_pressure:.2f}), offloading to worker")
                
        # Calculate confidence
        if decision.target_node == "gpu-master":
            decision.confidence = 0.8 if master_has_resources else 0.5
        else:
            decision.confidence = 0.7
            
        return decision

    async def _should_offload_for_memory(self, node_id: str, estimated_memory_gb: float) -> bool:
        """Determine if task should offload due to memory pressure."""
        pressure = self.metrics_collector.get_memory_pressure_score(node_id)
        snapshot = self.metrics_collector.get_latest_snapshot(node_id)
        if not snapshot:
            return True

        available_memory_gb = (snapshot.memory_total - snapshot.memory_used) / (1024**3)
        should_offload = (
            estimated_memory_gb > available_memory_gb
            or pressure > 0.8
            or available_memory_gb < 2.0
        )

        if should_offload:
            logger.info(
                "Memory offloading recommended",
                node=node_id,
                required_gb=estimated_memory_gb,
                available_gb=available_memory_gb,
                pressure=pressure,
            )

        return should_offload
        
    async def _execute_with_shared_resources(
        self,
        task_id: str,
        decision: OffloadingDecision,
        runtime_env: Optional[Dict],
    ) -> Dict[str, Any]:
        """Execute task using shared resources on master."""
        task_info = self._active_tasks[task_id]
        analysis = task_info["resource_analysis"]
        
        # Request shared resources if needed
        if decision.use_shared_resources:
            allocation_ids = []
            
            try:
                # Request CPU if needed
                if analysis.cpu_requirement > 1:
                    cpu_id = await self.resource_sharing_manager.request_resource(
                        node_id="gpu-master",
                        resource_type=ResourceType.CPU,
                        amount=analysis.cpu_requirement - 1,
                        priority=AllocationPriority.HIGH if analysis.priority == TaskPriority.HIGH else AllocationPriority.NORMAL,
                        duration=timedelta(hours=1),
                    )
                    allocation_ids.append(cpu_id)
                    
                # Request memory if needed
                if analysis.memory_requirement_mb > 2048:
                    memory_id = await self.resource_sharing_manager.request_resource(
                        node_id="gpu-master",
                        resource_type=ResourceType.MEMORY,
                        amount=analysis.memory_requirement_mb / 1024.0,  # Convert MB to GB
                        priority=AllocationPriority.NORMAL,
                        duration=timedelta(hours=1),
                    )
                    allocation_ids.append(memory_id)
                    
                # Request GPU if needed
                if analysis.gpu_requirement > 0:
                    gpu_id = await self.resource_sharing_manager.request_resource(
                        node_id="gpu-master",
                        resource_type=ResourceType.GPU,
                        amount=analysis.gpu_requirement,
                        priority=AllocationPriority.CRITICAL,
                        duration=timedelta(minutes=30),
                    )
                    allocation_ids.append(gpu_id)
                    
                decision.resource_allocation_id = allocation_ids[0] if allocation_ids else None
                
            except Exception as e:
                logger.error("Failed to request shared resources", task_id=task_id, error=str(e))
                # Fall back to regular execution
                
        # Create scheduling request
        scheduling_request = SchedulingRequest(
            task_id=task_id,
            requirements=analysis.to_resource_requirement(),
            priority=analysis.priority,
            strategy=SchedulingStrategy.PERFORMANCE_OPTIMIZED,
        )
        
        # Get scheduling decision
        scheduling_decision = await self.intelligent_scheduler.schedule_task(scheduling_request)
        decision.placement_group = scheduling_decision.placement_group
        
        # Execute on master with shared resources
        return await self._execute_on_master(task_id, decision, runtime_env)
        
    async def _execute_dynamic_balancing(
        self,
        task_id: str,
        decision: OffloadingDecision,
        runtime_env: Optional[Dict],
    ) -> Dict[str, Any]:
        """Execute with dynamic resource balancing."""
        # Similar to shared resources but with more sophisticated logic
        return await self._execute_with_shared_resources(task_id, decision, runtime_env)
        
    async def _execute_original_offloading(
        self,
        task_id: str,
        recommendation: OffloadingRecommendation,
        runtime_env: Optional[Dict],
    ) -> Dict[str, Any]:
        """Execute using original offloading approach with actual Ray job submission."""
        if not self._job_client:
            self._job_client = JobSubmissionClient(self.ray_dashboard_address)

        # Prepare command and resources
        command = " ".join(recommendation.process.cmdline)
        
        # Map target node to IP for resource pinning
        target_ip = self._get_node_ip(recommendation.target_node)
        entrypoint_resources = {f"node:{target_ip}": 0.01}
        
        # Combine runtime env
        full_runtime_env = runtime_env or {}
        full_runtime_env.update({
            "env_vars": {
                "OFFLOADING_TASK_ID": task_id,
                "EXECUTION_MODE": "offload_only"
            }
        })

        try:
            # Submit actual job to Ray
            job_id = self._job_client.submit_job(
                entrypoint=command,
                submission_id=f"job_{task_id}",
                runtime_env=full_runtime_env,
                entrypoint_resources=entrypoint_resources,
            )
            
            logger.info(
                "Ray job submitted successfully",
                task_id=task_id,
                job_id=job_id,
                target=recommendation.target_node,
                command=command[:50] + "..." if len(command) > 50 else command
            )
            
            return {"type": "ray_job", "job_id": job_id}
            
        except Exception as e:
            logger.error("Failed to submit Ray job", task_id=task_id, error=str(e))
            raise
        
    async def _execute_on_master(
        self,
        task_id: str,
        decision: OffloadingDecision,
        runtime_env: Optional[Dict],
    ) -> Dict[str, Any]:
        """Execute task on master node with resources."""
        task_info = self._active_tasks[task_id]
        process = task_info["recommendation"].process
        
        # Create Ray remote function for the process
        @ray.remote
        def execute_process(command: str, env_vars: Dict[str, str]) -> Dict[str, Any]:
            """Execute a process remotely."""
            import subprocess
            import os
            import time
            
            # Set environment variables
            for key, value in env_vars.items():
                os.environ[key] = value
                
            # Execute the command
            start_time = time.time()
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
            )
            end_time = time.time()
            
            return {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "execution_time": end_time - start_time,
            }
            
        # Prepare execution
        command = " ".join(process.cmdline)
        env_vars = {
            "OFFLOADING_TASK_ID": task_id,
            "EXECUTION_MODE": "shared_resources",
        }
        
        # Execute with Ray
        if decision.placement_group:
            # Execute with placement group
            remote_fn = execute_process.options(
                placement_group=decision.placement_group,
                placement_group_bundle_index=0,
            )
        else:
            # Apply scheduling strategy based on decision
            scheduling_options = {
                "num_cpus": task_info["resource_analysis"].cpu_requirement,
                "num_gpus": task_info["resource_analysis"].gpu_requirement,
            }
            
            # Add scheduling strategy for spreading tasks
            if task_info.get("spread_tasks", False):
                scheduling_options["scheduling_strategy"] = "SPREAD"
            
            # Add node-specific placement if target node is specified
            if decision.target_node and decision.target_node != "gpu-master":
                # Map node names to Ray node resources
                node_resource = f"node:{self._get_node_ip(decision.target_node)}"
                scheduling_options["resources"] = {node_resource: 0.001}
            
            remote_fn = execute_process.options(**scheduling_options)
            
        # Submit task
        future = remote_fn.remote(command, env_vars)
        
        return {
            "type": "ray_remote",
            "future": future,
            "node": "gpu-master",
        }
        
    async def stop(self) -> None:
        """Stop the executor and cancel all monitoring tasks."""
        logger.info("Stopping EnhancedOffloadingExecutor and cancelling active tasks")
        
        # Cancel all monitoring tasks
        for task_id, task in self._monitoring_tasks.items():
            if not task.done():
                task.cancel()
                
        if self._monitoring_tasks:
            # Wait for tasks to complete cancellation
            await asyncio.gather(*self._monitoring_tasks.values(), return_exceptions=True)
            self._monitoring_tasks.clear()

        # Stop child components
        if self.metrics_collector:
            await self.metrics_collector.stop()
        if self.resource_sharing_manager:
            await self.resource_sharing_manager.stop()

    async def _monitor_task(self, task_id: str, execution_result: Dict[str, Any]) -> None:
        """Monitor a running task."""
        try:
            if execution_result["type"] == "ray_remote":
                # Monitor Ray remote task
                future = execution_result["future"]
                
                while True:
                    try:
                        # Check if task is ready
                        ready, _ = ray.wait([future], timeout=1.0)
                        
                        if ready:
                            # Task completed
                            result = ray.get(future)
                            await self._complete_task(task_id, result)
                            break
                            
                    except ray.exceptions.RayTaskError as e:
                        # Task failed
                        await self._fail_task(task_id, str(e))
                        break
                    except asyncio.CancelledError:
                        logger.info("Task monitoring cancelled", task_id=task_id)
                        raise
                        
                    await asyncio.sleep(1)
                    
            elif execution_result["type"] == "ray_job":
                # Monitor Ray job
                job_id = execution_result["job_id"]
                await self._monitor_ray_job(task_id, job_id)
                
        except asyncio.CancelledError:
            logger.info("Monitoring task for task_id was cancelled", task_id=task_id)
            # Perform cleanup if needed
            if task_id in self._active_tasks:
                await self._fail_task(task_id, "Monitoring cancelled during shutdown")
        except Exception as e:
            logger.error("Task monitoring failed", task_id=task_id, error=str(e))
            await self._fail_task(task_id, str(e))
        finally:
            if task_id in self._monitoring_tasks:
                del self._monitoring_tasks[task_id]
            
    async def _monitor_ray_job(self, task_id: str, job_id: str) -> None:
        """Monitor a Ray job with retry logic for propagation delay."""
        if not self._job_client:
            return
            
        retry_count = 0
        max_retries = 3
        
        try:
            while True:
                try:
                    job_status = self._job_client.get_job_status(job_id)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    if "404" in str(e) and retry_count < max_retries:
                        retry_count += 1
                        logger.warning("Job not yet found, retrying...", job_id=job_id, retry=retry_count)
                        await asyncio.sleep(2)
                        continue
                    raise

                if job_status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.STOPPED}:
                    if job_status == JobStatus.SUCCEEDED:
                        await self._complete_task(task_id, {"status": "completed"})
                    else:
                        await self._fail_task(task_id, f"Job failed with status {job_status}")
                    break
                    
                await asyncio.sleep(5)
                
        except Exception as e:
            logger.error("Ray job monitoring failed", task_id=task_id, error=str(e))
            await self._fail_task(task_id, str(e))
            
    async def _complete_task(self, task_id: str, result: Dict[str, Any]) -> None:
        """Mark a task as completed."""
        if task_id in self._active_tasks:
            task = self._active_tasks[task_id]
            task["status"] = "completed"
            task["completed_at"] = datetime.now(UTC)
            task["result"] = result
            
            # Release resources
            decision = task.get("decision")
            if decision and decision.resource_allocation_id:
                await self.resource_sharing_manager.release_resource(decision.resource_allocation_id)
                
            if decision and decision.placement_group:
                try:
                    ray.remove_placement_group(decision.placement_group)
                except Exception:
                    pass
                    
            # Notify scheduler
            await self.intelligent_scheduler.complete_task(task_id)
            
            # Move to history
            self._task_history.append(task)
            del self._active_tasks[task_id]
            
            logger.info("Task completed successfully", task_id=task_id)
            
    async def _fail_task(self, task_id: str, error: str) -> None:
        """Mark a task as failed."""
        if task_id in self._active_tasks:
            task = self._active_tasks[task_id]
            task["status"] = "failed"
            task["failed_at"] = datetime.now(UTC)
            task["error"] = error
            
            # Release resources
            decision = task.get("decision")
            if decision and decision.resource_allocation_id:
                await self.resource_sharing_manager.release_resource(decision.resource_allocation_id)
                
            # Move to history
            self._task_history.append(task)
            del self._active_tasks[task_id]
            
            logger.error("Task failed", task_id=task_id, error=error)
            
    async def get_enhanced_statistics(self) -> Dict[str, Any]:
        """Get enhanced statistics about offloading operations."""
        stats = {
            "total_tasks": len(self._task_history) + len(self._active_tasks),
            "active_tasks": len(self._active_tasks),
            "completed_tasks": 0,
            "failed_tasks": 0,
            "by_mode": {},
            "by_decision": {},
            "resource_sharing_usage": 0,
            "average_execution_time": 0,
        }
        
        execution_times = []
        
        for task in self._task_history:
            if task["status"] == "completed":
                stats["completed_tasks"] += 1
            elif task["status"] == "failed":
                stats["failed_tasks"] += 1
                
            # Mode statistics
            decision = task.get("decision", {})
            mode = decision.get("mode", "unknown")
            stats["by_mode"][mode] = stats["by_mode"].get(mode, 0) + 1
            
            # Resource sharing usage
            if decision.get("use_shared_resources"):
                stats["resource_sharing_usage"] += 1
                
            # Execution time
            if "started_at" in task and "completed_at" in task:
                duration = (task["completed_at"] - task["started_at"]).total_seconds()
                execution_times.append(duration)
                
        if execution_times:
            stats["average_execution_time"] = sum(execution_times) / len(execution_times)
            
        # Add resource sharing manager stats
        if self.resource_sharing_manager:
            stats["resource_sharing"] = self.resource_sharing_manager.get_resource_status()
            
        # Add scheduler stats
        if self.intelligent_scheduler:
            stats["scheduler"] = self.intelligent_scheduler.get_scheduling_status()
            
        return stats
        
    def _get_node_ip(self, node_name: str) -> str:
        """Get the IP address for a node name."""
        # Map node names to their IP addresses based on cluster config
        node_ip_map = {
            "gpu-master": "192.168.1.100",
            "gpu1": "192.168.1.101", 
            "gpu2": "192.168.1.102",
            "ml-server": "192.168.1.102",
        }
        return node_ip_map.get(node_name, node_name)
