"""Tests for boost-aware offloading and scheduling integration."""

from __future__ import annotations

import pytest
from datetime import datetime, UTC, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from distributed_grid.config import ClusterConfig, NodeConfig
from distributed_grid.monitoring.resource_metrics import (
    ResourceMetricsCollector,
    ResourceSnapshot,
    ResourceType,
)
from distributed_grid.orchestration.resource_boost_manager import (
    ResourceBoostManager,
    ResourceBoost,
    ResourceBoostRequest,
)
from distributed_grid.orchestration.resource_sharing_manager import (
    ResourceSharingManager,
    SharingPolicy,
)
from distributed_grid.orchestration.intelligent_scheduler import (
    IntelligentScheduler,
    SchedulingRequest,
    ResourceRequirement,
    SchedulingStrategy,
    TaskPriority,
)
from distributed_grid.orchestration.enhanced_offloading_executor import (
    EnhancedOffloadingExecutor,
    OffloadingMode,
    ResourceAnalysis,
)
from distributed_grid.orchestration.offloading_detector import (
    ProcessInfo,
    OffloadingRecommendation,
    ProcessType,
)
from distributed_grid.orchestration.resource_sharing_types import AllocationPriority
from tests.conftest import get_test_cluster_config


@pytest.fixture
def cluster_config():
    """Create a test cluster configuration."""
    return get_test_cluster_config()


@pytest.fixture
def metrics_collector(cluster_config):
    """Create a metrics collector with test snapshots."""
    collector = ResourceMetricsCollector(cluster_config)
    
    # Create realistic snapshots
    memory_total = 32 * 1024**3  # 32 GB
    memory_used = 20 * 1024**3   # 20 GB used
    memory_available = memory_total - memory_used
    
    collector._latest_snapshot["gpu-master"] = ResourceSnapshot(
        node_id="gpu-master",
        node_name="gpu-master",
        timestamp=datetime.now(UTC),
        cpu_count=8,
        cpu_used=6,
        cpu_available=2,  # Low CPU available
        cpu_percent=75.0,
        memory_total=memory_total,
        memory_used=memory_used,
        memory_available=memory_available,
        memory_percent=(memory_used / memory_total) * 100,
        gpu_count=1,
        gpu_used=0,
        gpu_available=1,
        gpu_memory_total=16 * 1024**3,
        gpu_memory_used=0,
        gpu_memory_available=16 * 1024**3,
        load_avg=(2.5, 2.0, 1.8),
    )
    
    # Worker node with more resources
    worker_memory_total = 16 * 1024**3
    worker_memory_used = 4 * 1024**3
    collector._latest_snapshot["gpu1"] = ResourceSnapshot(
        node_id="gpu1",
        node_name="gpu1",
        timestamp=datetime.now(UTC),
        cpu_count=6,
        cpu_used=2,
        cpu_available=4,
        cpu_percent=33.3,
        memory_total=worker_memory_total,
        memory_used=worker_memory_used,
        memory_available=worker_memory_total - worker_memory_used,
        memory_percent=(worker_memory_used / worker_memory_total) * 100,
        gpu_count=1,
        gpu_used=0,
        gpu_available=1,
        gpu_memory_total=16 * 1024**3,
        gpu_memory_used=0,
        gpu_memory_available=16 * 1024**3,
        load_avg=(0.5, 0.4, 0.3),
    )
    
    return collector


@pytest.fixture
async def resource_sharing_manager(cluster_config, metrics_collector):
    """Create a resource sharing manager."""
    manager = ResourceSharingManager(
        cluster_config=cluster_config,
        metrics_collector=metrics_collector,
        policy=SharingPolicy.BALANCED,
    )
    await manager.start()
    yield manager
    await manager.stop()


@pytest.fixture
async def boost_manager(cluster_config, metrics_collector, resource_sharing_manager):
    """Create a boost manager."""
    manager = ResourceBoostManager(
        cluster_config=cluster_config,
        metrics_collector=metrics_collector,
        resource_sharing_manager=resource_sharing_manager,
    )
    await manager.initialize()
    yield manager
    # Cleanup: release any active boosts
    active_boosts = await manager.get_active_boosts()
    for boost in active_boosts:
        await manager.release_boost(boost.boost_id)


@pytest.mark.asyncio
class TestBoostAwareOffloading:
    """Test boost-aware offloading decisions."""
    
    async def test_offloading_without_boost_offloads_to_worker(
        self, cluster_config, metrics_collector
    ):
        """Test that without boosts, processes are offloaded when master lacks resources."""
        executor = EnhancedOffloadingExecutor(
            ssh_manager=None,
            cluster_config=cluster_config,
            metrics_collector=metrics_collector,
            mode=OffloadingMode.DYNAMIC_BALANCING,
            boost_manager=None,  # No boost manager
        )
        
        # Mock cluster summary to indicate high pressure to force offloading
        # Also ensure average pressure is high enough (> 0.7) to trigger offloading
        executor.metrics_collector.get_cluster_summary = Mock(return_value={
            "node_pressure_scores": {
                "gpu-master": 0.9,  # Very high pressure
                "gpu1": 0.3,
            }
        })
        
        # Mock _should_offload_for_memory to return True to force offloading
        executor._should_offload_for_memory = AsyncMock(return_value=True)
        
        process = ProcessInfo(
            pid=1234,
            name="cpu-intensive",
            cmdline=["python", "task.py"],
            cpu_percent=80.0,
            memory_mb=4096,
            gpu_memory_mb=0,
            process_type=ProcessType.COMPUTE_INTENSIVE,
        )
        
        recommendation = OffloadingRecommendation(
            process=process,
            source_node="gpu-master",
            target_node="gpu1",
            confidence=0.9,
            reason="insufficient resources",
            resource_match={},
            migration_complexity="low",
        )
        
        analysis = await executor._analyze_process_requirements(process)
        decision = await executor._make_offloading_decision(recommendation, analysis)
        
        # Without boosts, master has only 2 CPU available, task needs more
        # With high pressure, should offload to worker
        assert decision.target_node == "gpu1"
        assert decision.mode == OffloadingMode.OFFLOAD_ONLY
    
    async def test_offloading_with_cpu_boost_keeps_on_master(
        self, cluster_config, metrics_collector, boost_manager
    ):
        """Test that with CPU boost, processes can stay on master."""
        # Ensure boost_manager is initialized
        if not boost_manager._initialized:
            await boost_manager.initialize()
        
        # Create an active CPU boost
        boost = ResourceBoost(
            boost_id="test-cpu-boost",
            source_node="gpu1",
            target_node="gpu-master",
            resource_type=ResourceType.CPU,
            amount=4.0,  # Boost master with 4 CPUs
            allocated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            is_active=True,
        )
        boost_manager._active_boosts[boost.boost_id] = boost
        
        executor = EnhancedOffloadingExecutor(
            ssh_manager=None,
            cluster_config=cluster_config,
            metrics_collector=metrics_collector,
            mode=OffloadingMode.DYNAMIC_BALANCING,
            boost_manager=boost_manager,
        )
        
        # Mock cluster summary for low pressure
        executor.metrics_collector.get_cluster_summary = Mock(return_value={
            "node_pressure_scores": {
                "gpu-master": 0.4,
                "gpu1": 0.3,
            }
        })
        
        process = ProcessInfo(
            pid=1234,
            name="cpu-intensive",
            cmdline=["python", "task.py"],
            cpu_percent=50.0,
            memory_mb=2048,
            gpu_memory_mb=0,
            process_type=ProcessType.COMPUTE_INTENSIVE,
        )
        
        recommendation = OffloadingRecommendation(
            process=process,
            source_node="gpu-master",
            target_node="gpu1",
            confidence=0.9,
            reason="insufficient resources",
            resource_match={},
            migration_complexity="low",
        )
        
        analysis = await executor._analyze_process_requirements(process)
        # Task needs ~2 CPUs, master has 2 + 4 boosted = 6 available
        decision = await executor._make_offloading_decision(recommendation, analysis)
        
        # With boost, master should have enough resources
        assert decision.target_node == "gpu-master"
        assert "boost" in " ".join(decision.reasoning).lower() or "boosted" in " ".join(decision.reasoning).lower()
    
    async def test_offloading_with_memory_boost_keeps_on_master(
        self, cluster_config, metrics_collector, boost_manager
    ):
        """Test that with memory boost, memory-intensive processes can stay on master."""
        # Ensure boost_manager is initialized
        if not boost_manager._initialized:
            await boost_manager.initialize()
        
        # Create an active memory boost
        boost = ResourceBoost(
            boost_id="test-memory-boost",
            source_node="gpu1",
            target_node="gpu-master",
            resource_type=ResourceType.MEMORY,
            amount=8.0,  # Boost master with 8 GB
            allocated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            is_active=True,
        )
        boost_manager._active_boosts[boost.boost_id] = boost
        
        executor = EnhancedOffloadingExecutor(
            ssh_manager=None,
            cluster_config=cluster_config,
            metrics_collector=metrics_collector,
            mode=OffloadingMode.SHARE_AND_OFFLOAD,
            boost_manager=boost_manager,
        )
        
        process = ProcessInfo(
            pid=1234,
            name="memory-intensive",
            cmdline=["python", "task.py"],
            cpu_percent=20.0,
            memory_mb=10 * 1024,  # 10 GB memory requirement
            gpu_memory_mb=0,
            process_type=ProcessType.DATA_PROCESSING,
        )
        
        recommendation = OffloadingRecommendation(
            process=process,
            source_node="gpu-master",
            target_node="gpu1",
            confidence=0.9,
            reason="insufficient memory",
            resource_match={},
            migration_complexity="low",
        )
        
        analysis = await executor._analyze_process_requirements(process)
        # Master has ~12 GB available + 8 GB boosted = 20 GB
        decision = await executor._make_offloading_decision(recommendation, analysis)
        
        # With memory boost, master should have enough
        assert decision.target_node == "gpu-master"
        assert decision.use_shared_resources is True
    
    async def test_offloading_considers_multiple_boosts(
        self, cluster_config, metrics_collector, boost_manager
    ):
        """Test that multiple boosts are aggregated correctly."""
        # Ensure boost_manager is initialized
        if not boost_manager._initialized:
            await boost_manager.initialize()
        
        # Create multiple boosts
        cpu_boost = ResourceBoost(
            boost_id="cpu-boost",
            source_node="gpu1",
            target_node="gpu-master",
            resource_type=ResourceType.CPU,
            amount=2.0,
            allocated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            is_active=True,
        )
        memory_boost = ResourceBoost(
            boost_id="memory-boost",
            source_node="gpu1",
            target_node="gpu-master",
            resource_type=ResourceType.MEMORY,
            amount=4.0,
            allocated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            is_active=True,
        )
        boost_manager._active_boosts[cpu_boost.boost_id] = cpu_boost
        boost_manager._active_boosts[memory_boost.boost_id] = memory_boost
        
        executor = EnhancedOffloadingExecutor(
            ssh_manager=None,
            cluster_config=cluster_config,
            metrics_collector=metrics_collector,
            mode=OffloadingMode.DYNAMIC_BALANCING,
            boost_manager=boost_manager,
        )
        
        executor.metrics_collector.get_cluster_summary = Mock(return_value={
            "node_pressure_scores": {
                "gpu-master": 0.5,
                "gpu1": 0.3,
            }
        })
        
        process = ProcessInfo(
            pid=1234,
            name="mixed-workload",
            cmdline=["python", "task.py"],
            cpu_percent=60.0,
            memory_mb=6 * 1024,  # 6 GB
            gpu_memory_mb=0,
            process_type=ProcessType.DATA_PROCESSING,
        )
        
        recommendation = OffloadingRecommendation(
            process=process,
            source_node="gpu-master",
            target_node="gpu1",
            confidence=0.9,
            reason="insufficient resources",
            resource_match={},
            migration_complexity="low",
        )
        
        analysis = await executor._analyze_process_requirements(process)
        decision = await executor._make_offloading_decision(recommendation, analysis)
        
        # Master has 2 CPU + 2 boosted = 4, and 12 GB + 4 GB boosted = 16 GB
        # Should be enough for the task
        assert decision.target_node == "gpu-master"


@pytest.mark.asyncio
class TestBoostAwareScheduling:
    """Test boost-aware scheduling decisions."""
    
    async def test_scheduler_rejects_without_boost_when_insufficient(
        self, cluster_config, metrics_collector, resource_sharing_manager
    ):
        """Test that scheduler rejects tasks when node lacks resources and no boost."""
        scheduler = IntelligentScheduler(
            cluster_config=cluster_config,
            metrics_collector=metrics_collector,
            resource_sharing_manager=resource_sharing_manager,
            boost_manager=None,  # No boost manager
        )
        
        request = SchedulingRequest(
            task_id="test-task-1",
            requirements=ResourceRequirement(
                cpu_count=4.0,  # Master only has 2 available
                memory_mb=2048,
                gpu_count=0,
            ),
            strategy=SchedulingStrategy.BEST_FIT,
        )
        
        # Should raise error or return no eligible nodes
        eligible_nodes = await scheduler._filter_eligible_nodes(
            request,
            metrics_collector.get_all_latest_snapshots(),
        )
        
        # Master should not be eligible (only 2 CPU available, needs 4)
        assert "gpu-master" not in eligible_nodes
    
    async def test_scheduler_accepts_with_cpu_boost(
        self, cluster_config, metrics_collector, resource_sharing_manager, boost_manager
    ):
        """Test that scheduler accepts tasks when CPU boost makes node eligible."""
        # Ensure boost_manager is initialized
        if not boost_manager._initialized:
            await boost_manager.initialize()
        
        # Create CPU boost
        boost = ResourceBoost(
            boost_id="cpu-boost",
            source_node="gpu1",
            target_node="gpu-master",
            resource_type=ResourceType.CPU,
            amount=3.0,  # Boost with 3 CPUs
            allocated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            is_active=True,
        )
        boost_manager._active_boosts[boost.boost_id] = boost
        
        scheduler = IntelligentScheduler(
            cluster_config=cluster_config,
            metrics_collector=metrics_collector,
            resource_sharing_manager=resource_sharing_manager,
            boost_manager=boost_manager,
        )
        
        request = SchedulingRequest(
            task_id="test-task-2",
            requirements=ResourceRequirement(
                cpu_count=4.0,  # Master has 2 + 3 boosted = 5 available
                memory_mb=2048,
                gpu_count=0,
            ),
            strategy=SchedulingStrategy.BEST_FIT,
        )
        
        eligible_nodes = await scheduler._filter_eligible_nodes(
            request,
            metrics_collector.get_all_latest_snapshots(),
        )
        
        # Master should now be eligible with boost
        assert "gpu-master" in eligible_nodes
    
    async def test_scheduler_accepts_with_memory_boost(
        self, cluster_config, metrics_collector, resource_sharing_manager, boost_manager
    ):
        """Test that scheduler accepts tasks when memory boost makes node eligible."""
        # Ensure boost_manager is initialized
        if not boost_manager._initialized:
            await boost_manager.initialize()
        
        # Create memory boost
        boost = ResourceBoost(
            boost_id="memory-boost",
            source_node="gpu1",
            target_node="gpu-master",
            resource_type=ResourceType.MEMORY,
            amount=6.0,  # Boost with 6 GB
            allocated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            is_active=True,
        )
        boost_manager._active_boosts[boost.boost_id] = boost
        
        scheduler = IntelligentScheduler(
            cluster_config=cluster_config,
            metrics_collector=metrics_collector,
            resource_sharing_manager=resource_sharing_manager,
            boost_manager=boost_manager,
        )
        
        request = SchedulingRequest(
            task_id="test-task-3",
            requirements=ResourceRequirement(
                cpu_count=1.0,
                memory_mb=16 * 1024,  # 16 GB - master has ~12 + 6 boosted = 18 GB
                gpu_count=0,
            ),
            strategy=SchedulingStrategy.BEST_FIT,
        )
        
        eligible_nodes = await scheduler._filter_eligible_nodes(
            request,
            metrics_collector.get_all_latest_snapshots(),
        )
        
        # Master should be eligible with memory boost
        assert "gpu-master" in eligible_nodes
    
    async def test_scheduler_handles_boost_manager_none_gracefully(
        self, cluster_config, metrics_collector, resource_sharing_manager
    ):
        """Test that scheduler works correctly when boost_manager is None."""
        scheduler = IntelligentScheduler(
            cluster_config=cluster_config,
            metrics_collector=metrics_collector,
            resource_sharing_manager=resource_sharing_manager,
            boost_manager=None,
        )
        
        request = SchedulingRequest(
            task_id="test-task-4",
            requirements=ResourceRequirement(
                cpu_count=1.0,
                memory_mb=1024,
                gpu_count=0,
            ),
            strategy=SchedulingStrategy.BEST_FIT,
        )
        
        # Should not raise error
        eligible_nodes = await scheduler._filter_eligible_nodes(
            request,
            metrics_collector.get_all_latest_snapshots(),
        )
        
        # Should return some eligible nodes (worker has resources)
        assert len(eligible_nodes) > 0


@pytest.mark.asyncio
class TestBoostAwareIntegration:
    """Integration tests for boost-aware system."""
    
    async def test_full_workflow_with_boost(
        self, cluster_config, metrics_collector, resource_sharing_manager, boost_manager
    ):
        """Test full workflow: create boost, schedule task, make offloading decision."""
        # 1. Create a CPU boost
        boost_request = ResourceBoostRequest(
            target_node="gpu-master",
            resource_type=ResourceType.CPU,
            amount=4.0,
            priority=AllocationPriority.HIGH,
        )
        
        # Mock the resource sharing manager to return an allocation ID
        original_request = resource_sharing_manager.request_resource
        resource_sharing_manager.request_resource = AsyncMock(return_value="alloc-123")
        
        # Mock Ray operations to avoid requiring a real Ray cluster
        with patch.object(boost_manager, '_add_ray_resources', new_callable=AsyncMock) as mock_ray:
            mock_ray.return_value = None
            boost_id = await boost_manager.request_boost(boost_request)
        assert boost_id is not None
        
        # 2. Verify boost is active
        active_boosts = await boost_manager.get_active_boosts(target_node="gpu-master")
        assert len(active_boosts) > 0
        
        # 3. Create scheduler with boost manager
        scheduler = IntelligentScheduler(
            cluster_config=cluster_config,
            metrics_collector=metrics_collector,
            resource_sharing_manager=resource_sharing_manager,
            boost_manager=boost_manager,
        )
        
        # 4. Schedule a task that needs boosted resources
        request = SchedulingRequest(
            task_id="boosted-task",
            requirements=ResourceRequirement(
                cpu_count=5.0,  # Needs more than base 2, but less than 2+4=6
                memory_mb=2048,
                gpu_count=0,
            ),
        )
        
        # Should be able to schedule on master with boost
        eligible_nodes = await scheduler._filter_eligible_nodes(
            request,
            metrics_collector.get_all_latest_snapshots(),
        )
        assert "gpu-master" in eligible_nodes
        
        # 5. Create offloading executor with boost manager
        executor = EnhancedOffloadingExecutor(
            ssh_manager=None,
            cluster_config=cluster_config,
            metrics_collector=metrics_collector,
            mode=OffloadingMode.DYNAMIC_BALANCING,
            boost_manager=boost_manager,
        )
        
        executor.metrics_collector.get_cluster_summary = Mock(return_value={
            "node_pressure_scores": {
                "gpu-master": 0.4,
                "gpu1": 0.3,
            }
        })
        
        # 6. Make offloading decision
        process = ProcessInfo(
            pid=5678,
            name="boosted-process",
            cmdline=["python", "task.py"],
            cpu_percent=70.0,
            memory_mb=2048,
            gpu_memory_mb=0,
            process_type=ProcessType.COMPUTE_INTENSIVE,
        )
        
        recommendation = OffloadingRecommendation(
            process=process,
            source_node="gpu-master",
            target_node="gpu1",
            confidence=0.9,
            reason="test",
            resource_match={},
            migration_complexity="low",
        )
        
        analysis = await executor._analyze_process_requirements(process)
        decision = await executor._make_offloading_decision(recommendation, analysis)
        
        # Should prefer master with boosted resources
        assert decision.target_node == "gpu-master"
    
    async def test_automatic_offloading_on_boost_activation(
        self, cluster_config, metrics_collector, resource_sharing_manager
    ):
        """Test that automatic offloading is triggered when a boost is activated."""
        from distributed_grid.orchestration.offloading_detector import OffloadingDetector
        from distributed_grid.core.ssh_manager import SSHManager
        
        # Create a mock offloading detector
        mock_detector = Mock(spec=OffloadingDetector)
        mock_detector.detect_offloading_candidates = AsyncMock(return_value=[])
        
        # Create a mock enhanced executor
        mock_executor = Mock()
        mock_executor.execute_offloading = AsyncMock(return_value="task-123")
        
        # Create boost manager with callback
        callback_called = []
        async def test_callback(boost):
            callback_called.append(boost)
            # Simulate offloading trigger
            if mock_detector and mock_executor:
                recommendations = await mock_detector.detect_offloading_candidates()
                for rec in recommendations[:5]:
                    await mock_executor.execute_offloading(rec)
        
        boost_manager = ResourceBoostManager(
            cluster_config=cluster_config,
            metrics_collector=metrics_collector,
            resource_sharing_manager=resource_sharing_manager,
            on_boost_activated=test_callback,
        )
        await boost_manager.initialize()
        
        # Mock resource sharing manager
        resource_sharing_manager.request_resource = AsyncMock(return_value="alloc-123")
        
        # Mock Ray operations
        with patch.object(boost_manager, '_add_ray_resources', new_callable=AsyncMock) as mock_ray:
            mock_ray.return_value = None
            
            # Create a boost for master node
            boost_request = ResourceBoostRequest(
                target_node="gpu-master",
                resource_type=ResourceType.CPU,
                amount=4.0,
                priority=AllocationPriority.HIGH,
            )
            
            boost_id = await boost_manager.request_boost(boost_request)
            assert boost_id is not None
            
            # Verify callback was called
            assert len(callback_called) == 1
            assert callback_called[0].target_node == "gpu-master"
            assert callback_called[0].boost_id == boost_id
            
            # Verify offloading detector was called
            mock_detector.detect_offloading_candidates.assert_called_once()
