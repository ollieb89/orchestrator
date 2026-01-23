"""Tests for intelligent resource sharing system."""

import pytest
import asyncio
import time
from datetime import datetime, UTC, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any

import ray
import yaml

from distributed_grid.config import ClusterConfig, NodeConfig
from distributed_grid.monitoring.resource_metrics import (
    ResourceMetricsCollector,
    ResourceSnapshot,
    ResourceType,
)
from distributed_grid.orchestration.resource_sharing_manager import (
    ResourceSharingManager,
    SharingPolicy,
    ResourceRequest,
    AllocationPriority,
    ResourceAllocation,
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
from distributed_grid.orchestration.resource_sharing_orchestrator import (
    ResourceSharingOrchestrator,
)
from distributed_grid.orchestration.offloading_detector import (
    ProcessInfo,
    OffloadingRecommendation,
    ProcessType,
)


@pytest.fixture
def cluster_config():
    """Create a test cluster configuration."""
    config = ClusterConfig(
        name="test-cluster",
        nodes=[
            NodeConfig(
                name="test-master",
                host="localhost",
                user="test",
                role="master",
                cpu_count=8,
                memory_gb=32,
                gpu_count=1,
                port=22,
                tags=["master", "gpu"],
            ),
            NodeConfig(
                name="test-worker-1",
                host="worker1",
                user="test",
                role="worker",
                cpu_count=6,
                memory_gb=16,
                gpu_count=1,
                port=22,
                tags=["worker", "gpu"],
            ),
            NodeConfig(
                name="test-worker-2",
                host="worker2",
                user="test",
                role="worker",
                cpu_count=4,
                memory_gb=8,
                gpu_count=0,
                port=22,
                tags=["worker"],
            ),
        ],
    )
    config.execution = {
        "resource_sharing": {
            "enabled": True,
            "mode": "dynamic_balancing",
            "policy": "balanced",
            "rebalance_interval_seconds": 5.0,
            "monitoring_interval_seconds": 1.0,
            "thresholds": {
                "cpu_pressure_high": 0.8,
                "cpu_pressure_low": 0.3,
                "memory_pressure_high": 0.8,
                "memory_pressure_low": 0.3,
                "gpu_pressure_high": 0.8,
                "gpu_pressure_low": 0.3,
                "excess_threshold": 0.2,
            },
        }
    }
    return config


@pytest.fixture
def mock_ssh_manager():
    """Create a mock SSH manager."""
    manager = Mock()
    manager.run_command = AsyncMock(return_value=Mock(exit_status=0, stdout=""))
    return manager


@pytest.fixture
async def resource_snapshots():
    """Create test resource snapshots."""
    return {
        "test-master": ResourceSnapshot(
            node_id="test-master",
            node_name="test-master",
            timestamp=datetime.now(UTC),
            cpu_count=8,
            cpu_used=4,
            cpu_available=4,
            cpu_percent=50.0,
            memory_total=32 * 1024**3,
            memory_used=16 * 1024**3,
            memory_available=16 * 1024**3,
            memory_percent=50.0,
            gpu_count=1,
            gpu_used=0,
            gpu_available=1,
            gpu_memory_total=16 * 1024**3,
            gpu_memory_used=0,
            gpu_memory_available=16 * 1024**3,
        ),
        "test-worker-1": ResourceSnapshot(
            node_id="test-worker-1",
            node_name="test-worker-1",
            timestamp=datetime.now(UTC),
            cpu_count=6,
            cpu_used=2,
            cpu_available=4,
            cpu_percent=33.3,
            memory_total=16 * 1024**3,
            memory_used=4 * 1024**3,
            memory_available=12 * 1024**3,
            memory_percent=25.0,
            gpu_count=1,
            gpu_used=0,
            gpu_available=1,
            gpu_memory_total=16 * 1024**3,
            gpu_memory_used=0,
            gpu_memory_available=16 * 1024**3,
        ),
        "test-worker-2": ResourceSnapshot(
            node_id="test-worker-2",
            node_name="test-worker-2",
            timestamp=datetime.now(UTC),
            cpu_count=4,
            cpu_used=1,
            cpu_available=3,
            cpu_percent=25.0,
            memory_total=8 * 1024**3,
            memory_used=2 * 1024**3,
            memory_available=6 * 1024**3,
            memory_percent=25.0,
            gpu_count=0,
            gpu_used=0,
            gpu_available=0,
            gpu_memory_total=0,
            gpu_memory_used=0,
            gpu_memory_available=0,
        ),
    }


class TestResourceMetricsCollector:
    """Test the resource metrics collector."""
    
    @pytest.fixture
    async def collector(self, cluster_config):
        """Create a resource metrics collector."""
        collector = ResourceMetricsCollector(
            cluster_config,
            collection_interval=0.1,
            history_size=10,
        )
        yield collector
        await collector.stop()
        
    @patch('distributed_grid.monitoring.resource_metrics.ray')
    async def test_collect_metrics(self, mock_ray, collector, resource_snapshots):
        """Test metric collection."""
        # Mock Ray functions
        mock_ray.is_initialized.return_value = True
        mock_ray.cluster_resources.return_value = {"CPU": 18, "GPU": 2}
        mock_ray.available_resources.return_value = {"CPU": 9, "GPU": 2}
        mock_ray.nodes.return_value = [
            {
                "NodeManagerAddress": "localhost",
                "Resources": {"CPU": 8, "GPU": 1},
            },
            {
                "NodeManagerAddress": "worker1",
                "Resources": {"CPU": 6, "GPU": 1},
            },
            {
                "NodeManagerAddress": "worker2",
                "Resources": {"CPU": 4, "GPU": 0},
            },
        ]
        
        # Start collection
        await collector.start()
        
        # Wait for collection
        await asyncio.sleep(0.2)
        
        # Check snapshots
        snapshots = collector.get_all_latest_snapshots()
        assert len(snapshots) == 3
        assert "test-master" in snapshots
        assert "test-worker-1" in snapshots
        assert "test-worker-2" in snapshots
        
        # Check cluster summary
        summary = collector.get_cluster_summary()
        assert summary["total_nodes"] == 3
        assert summary["total_cpu"] == 18
        assert summary["total_gpu"] == 2
        
    async def test_resource_trends(self, collector):
        """Test resource trend analysis."""
        # Create mock history
        now = datetime.now(UTC)
        
        # Simulate increasing CPU usage
        for i in range(5):
            snapshot = ResourceSnapshot(
                node_id="test-node",
                node_name="test-node",
                timestamp=now - timedelta(seconds=i * 10),
                cpu_count=8,
                cpu_used=2 + i,
                cpu_available=6 - i,
                cpu_percent=25.0 + i * 12.5,
                memory_total=16 * 1024**3,
                memory_used=8 * 1024**3,
                memory_available=8 * 1024**3,
                memory_percent=50.0,
                gpu_count=1,
                gpu_used=0,
                gpu_available=1,
                gpu_memory_total=16 * 1024**3,
                gpu_memory_used=0,
                gpu_memory_available=16 * 1024**3,
            )
            collector._resource_history["test-node"] = collector._resource_history.get("test-node", [])
            collector._resource_history["test-node"].append(snapshot)
            
        # Get trend
        trend = collector.get_resource_trend("test-node", ResourceType.CPU)
        assert trend is not None
        assert trend.resource_type == ResourceType.CPU
        assert trend.trend_5min > 0  # Increasing trend
        assert trend.predicted_usage_5min > trend.current_value


class TestResourceSharingManager:
    """Test the resource sharing manager."""
    
    @pytest.fixture
    async def manager(self, cluster_config):
        """Create a resource sharing manager."""
        # Create mock metrics collector
        metrics_collector = Mock()
        metrics_collector.get_all_latest_snapshots.return_value = {}
        
        manager = ResourceSharingManager(
            cluster_config,
            metrics_collector,
            policy=SharingPolicy.BALANCED,
            rebalance_interval=0.1,
        )
        yield manager
        await manager.stop()
        
    async def test_resource_request(self, manager):
        """Test resource request handling."""
        # Mock snapshots with available resources
        snapshots = {
            "test-worker-1": ResourceSnapshot(
                node_id="test-worker-1",
                node_name="test-worker-1",
                timestamp=datetime.now(UTC),
                cpu_count=6,
                cpu_used=2,
                cpu_available=4,
                cpu_percent=33.3,
                memory_total=16 * 1024**3,
                memory_used=4 * 1024**3,
                memory_available=12 * 1024**3,
                memory_percent=25.0,
                gpu_count=1,
                gpu_used=0,
                gpu_available=1,
                gpu_memory_total=16 * 1024**3,
                gpu_memory_used=0,
                gpu_memory_available=16 * 1024**3,
            ),
        }
        
        manager.metrics_collector.get_all_latest_snapshots.return_value = snapshots
        
        # Start manager
        await manager.start()
        
        # Request resources
        request_id = await manager.request_resource(
            node_id="test-master",
            resource_type=ResourceType.CPU,
            amount=2.0,
            priority=AllocationPriority.HIGH,
            duration=timedelta(minutes=5),
        )
        
        assert request_id is not None
        assert request_id.startswith("req_")
        
        # Check request was added
        assert len(manager._resource_requests) == 1
        assert manager._resource_requests[0].node_id == "test-master"
        assert manager._resource_requests[0].amount == 2.0
        
    @patch('distributed_grid.orchestration.resource_sharing_manager.ray')
    async def test_resource_allocation(self, mock_ray, manager):
        """Test resource allocation."""
        # Mock Ray placement group
        mock_pg = Mock()
        mock_ray.util.placement_group.return_value = mock_pg
        mock_ray.get.return_value = True
        
        # Create allocation
        allocation = ResourceAllocation(
            allocation_id="test-alloc",
            request_id="test-req",
            source_node="test-worker-1",
            target_node="test-master",
            resource_type=ResourceType.CPU,
            amount=2.0,
        )
        
        # Execute allocation
        result = await manager._execute_allocation(allocation)
        
        assert result is True
        assert allocation.allocation_id in manager._placement_groups
        assert manager._shared_resources["test-worker-1"][ResourceType.CPU] == 2.0
        
    async def test_cleanup_expired(self, manager):
        """Test cleanup of expired requests and allocations."""
        # Add expired request
        expired_request = ResourceRequest(
            request_id="expired",
            node_id="test-node",
            resource_type=ResourceType.CPU,
            amount=1.0,
            priority=AllocationPriority.NORMAL,
            timeout=timedelta(seconds=0),  # Already expired
        )
        manager._resource_requests.append(expired_request)
        
        # Add expired allocation
        expired_allocation = ResourceAllocation(
            allocation_id="expired-alloc",
            request_id="test",
            source_node="test-worker",
            target_node="test-master",
            resource_type=ResourceType.CPU,
            amount=1.0,
            lease_duration=timedelta(seconds=0),  # Already expired
        )
        manager._active_allocations.append(expired_allocation)
        
        # Cleanup
        await manager._cleanup_expired()
        
        # Check cleanup
        assert len(manager._resource_requests) == 0
        assert len(manager._active_allocations) == 0


class TestIntelligentScheduler:
    """Test the intelligent scheduler."""
    
    @pytest.fixture
    async def scheduler(self, cluster_config):
        """Create an intelligent scheduler."""
        # Create mock dependencies
        metrics_collector = Mock()
        resource_sharing_manager = Mock()
        
        scheduler = IntelligentScheduler(
            cluster_config,
            metrics_collector,
            resource_sharing_manager,
        )
        return scheduler
        
    async def test_schedule_task(self, scheduler, resource_snapshots):
        """Test task scheduling."""
        # Mock snapshots
        scheduler.metrics_collector.get_all_latest_snapshots.return_value = resource_snapshots
        
        # Create scheduling request
        request = SchedulingRequest(
            task_id="test-task",
            requirements=ResourceRequirement(
                cpu_count=2.0,
                memory_mb=4096,
                gpu_count=0,
            ),
            priority=TaskPriority.NORMAL,
            strategy=SchedulingStrategy.BEST_FIT,
        )
        
        # Schedule task
        decision = await scheduler.schedule_task(request)
        
        assert decision.task_id == "test-task"
        assert decision.node_id in ["test-master", "test-worker-1", "test-worker-2"]
        assert decision.confidence > 0
        assert len(decision.reasoning) > 0
        
        # Check task is tracked
        assert request.task_id in scheduler._active_tasks
        
    async def test_select_best_fit(self, scheduler, resource_snapshots):
        """Test best-fit node selection."""
        request = SchedulingRequest(
            task_id="test",
            requirements=ResourceRequirement(cpu_count=2.0, memory_mb=2048),
        )
        
        # Select best fit
        best_node = scheduler._select_best_fit(
            request,
            list(resource_snapshots.keys()),
            resource_snapshots,
        )
        
        # Should select worker-2 (lowest utilization)
        assert best_node == "test-worker-2"
        
    async def test_load_balanced_selection(self, scheduler, resource_snapshots):
        """Test load-balanced node selection."""
        request = SchedulingRequest(
            task_id="test",
            requirements=ResourceRequirement(cpu_count=1.0, memory_mb=1024),
        )
        
        # Select load balanced
        best_node = scheduler._select_load_balanced(
            request,
            list(resource_snapshots.keys()),
            resource_snapshots,
        )
        
        # Should select node with lowest pressure
        assert best_node == "test-worker-2"
        
    def test_calculate_confidence(self, scheduler):
        """Test confidence calculation."""
        # High confidence snapshot
        snapshot = ResourceSnapshot(
            node_id="test",
            node_name="test",
            timestamp=datetime.now(UTC),
            cpu_count=8,
            cpu_used=2,
            cpu_available=6,
            cpu_percent=25.0,
            memory_total=16 * 1024**3,
            memory_used=4 * 1024**3,
            memory_available=12 * 1024**3,
            memory_percent=25.0,
            gpu_count=1,
            gpu_used=0,
            gpu_available=1,
            gpu_memory_total=16 * 1024**3,
            gpu_memory_used=0,
            gpu_memory_available=16 * 1024**3,
        )
        
        requirements = ResourceRequirement(cpu_count=2.0, memory_mb=2048)
        
        confidence = scheduler._calculate_confidence(snapshot, requirements)
        assert confidence > 0.5  # Should be high confidence
        
        # Low confidence snapshot
        snapshot_high_pressure = ResourceSnapshot(
            node_id="test",
            node_name="test",
            timestamp=datetime.now(UTC),
            cpu_count=8,
            cpu_used=7,
            cpu_available=1,
            cpu_percent=87.5,
            memory_total=16 * 1024**3,
            memory_used=14 * 1024**3,
            memory_available=2 * 1024**3,
            memory_percent=87.5,
            gpu_count=1,
            gpu_used=1,
            gpu_available=0,
            gpu_memory_total=16 * 1024**3,
            gpu_memory_used=14 * 1024**3,
            gpu_memory_available=2 * 1024**3,
        )
        
        confidence = scheduler._calculate_confidence(snapshot_high_pressure, requirements)
        assert confidence < 0.5  # Should be low confidence


class TestEnhancedOffloadingExecutor:
    """Test the enhanced offloading executor."""
    
    @pytest.fixture
    async def executor(self, cluster_config, mock_ssh_manager):
        """Create an enhanced offloading executor."""
        executor = EnhancedOffloadingExecutor(
            mock_ssh_manager,
            cluster_config,
            mode=OffloadingMode.DYNAMIC_BALANCING,
        )
        return executor
        
    async def test_analyze_process_requirements(self, executor):
        """Test process resource analysis."""
        # Create test process
        process = ProcessInfo(
            pid=1234,
            name="test-process",
            cmdline=["python", "test.py"],
            cpu_percent=50.0,
            memory_mb=2048,
            gpu_memory_mb=0,
            process_type=ProcessType.DATA_PROCESSING,
            age_seconds=300,
        )
        
        # Analyze requirements
        analysis = await executor._analyze_process_requirements(process)
        
        assert isinstance(analysis, ResourceAnalysis)
        assert analysis.cpu_requirement >= 1.0
        assert analysis.memory_requirement_mb >= 1024
        assert analysis.gpu_requirement == 0
        assert analysis.priority == TaskPriority.NORMAL
        
    async def test_make_offloading_decision(self, executor, resource_snapshots):
        """Test offloading decision making."""
        # Create mock components
        executor.metrics_collector = Mock()
        executor.metrics_collector.get_all_latest_snapshots.return_value = resource_snapshots
        executor.metrics_collector.get_cluster_summary.return_value = {
            "node_pressure_scores": {
                "test-master": 0.5,
                "test-worker-1": 0.3,
                "test-worker-2": 0.2,
            }
        }
        
        # Create test data
        process = ProcessInfo(
            pid=1234,
            name="test",
            cmdline=["python", "test.py"],
            cpu_percent=25.0,
            memory_mb=1024,
            gpu_memory_mb=0,
        )
        recommendation = OffloadingRecommendation(
            process=process,
            target_node="test-worker-1",
            score=0.8,
            reason="Test",
        )
        analysis = ResourceAnalysis(
            process_info=process,
            cpu_requirement=2.0,
            memory_requirement_mb=2048,
            gpu_requirement=0,
        )
        
        # Make decision
        decision = await executor._make_offloading_decision(recommendation, analysis)
        
        assert decision.mode in [OffloadingMode.SHARE_AND_OFFLOAD, OffloadingMode.DYNAMIC_BALANCING]
        assert decision.target_node is not None
        assert decision.confidence > 0
        assert len(decision.reasoning) > 0
        
    @patch('distributed_grid.orchestration.enhanced_offloading_executor.ray')
    async def test_execute_with_shared_resources(self, mock_ray, executor):
        """Test execution with shared resources."""
        # Mock Ray remote function
        mock_future = Mock()
        mock_ray.remote.return_value.options.return_value.remote.return_value = mock_future
        
        # Create test decision
        decision = Mock()
        decision.placement_group = None
        decision.resource_allocation_id = None
        
        # Create task info
        executor._active_tasks["test"] = {
            "recommendation": Mock(),
            "resource_analysis": ResourceAnalysis(
                process_info=Mock(),
                cpu_requirement=2.0,
                memory_requirement_mb=2048,
                gpu_requirement=0,
            ),
            "decision": decision,
        }
        
        # Execute
        result = await executor._execute_on_master("test", decision, {})
        
        assert result["type"] == "ray_remote"
        assert result["node"] == "gpu-master"
        assert "future" in result


class TestResourceSharingOrchestrator:
    """Test the resource sharing orchestrator."""
    
    @pytest.fixture
    async def orchestrator(self, cluster_config, mock_ssh_manager):
        """Create a resource sharing orchestrator."""
        orchestrator = ResourceSharingOrchestrator(
            cluster_config,
            mock_ssh_manager,
        )
        yield orchestrator
        await orchestrator.stop()
        
    @patch('distributed_grid.orchestration.resource_sharing_orchestrator.ray')
    async def test_initialize_with_sharing(self, mock_ray, orchestrator):
        """Test initialization with resource sharing enabled."""
        mock_ray.is_initialized.return_value = True
        
        # Initialize
        await orchestrator.initialize()
        
        assert orchestrator._initialized is True
        assert orchestrator.metrics_collector is not None
        assert orchestrator.resource_sharing_manager is not None
        assert orchestrator.intelligent_scheduler is not None
        assert orchestrator.enhanced_executor is not None
        
    async def test_get_cluster_status(self, orchestrator):
        """Test getting cluster status."""
        # Mock components
        orchestrator.metrics_collector = Mock()
        orchestrator.metrics_collector.get_cluster_summary.return_value = {
            "total_nodes": 3,
            "total_cpu": 18,
        }
        orchestrator.resource_sharing_manager = Mock()
        orchestrator.resource_sharing_manager.get_resource_status.return_value = {
            "active_allocations": 2,
        }
        orchestrator.intelligent_scheduler = Mock()
        orchestrator.intelligent_scheduler.get_scheduling_status.return_value = {
            "active_tasks": 1,
        }
        orchestrator.enhanced_executor = Mock()
        orchestrator.enhanced_executor.get_enhanced_statistics.return_value = {
            "total_tasks": 10,
        }
        
        # Get status
        status = await orchestrator.get_cluster_status()
        
        assert status["resource_sharing_enabled"] is True
        assert "metrics" in status
        assert "resource_sharing" in status
        assert "scheduler" in status
        assert "executor" in status
        
    async def test_request_resources(self, orchestrator):
        """Test resource request through orchestrator."""
        # Mock resource sharing manager
        orchestrator.resource_sharing_manager = Mock()
        orchestrator.resource_sharing_manager.request_resource = AsyncMock(
            return_value="req-123"
        )
        
        # Request resources
        request_id = await orchestrator.request_resources(
            node_id="test-master",
            resource_type="cpu",
            amount=2.0,
            priority="high",
            duration_minutes=30,
        )
        
        assert request_id == "req-123"
        orchestrator.resource_sharing_manager.request_resource.assert_called_once()
        
    async def test_get_node_resource_snapshots(self, orchestrator):
        """Test getting node resource snapshots."""
        # Mock metrics collector
        orchestrator.metrics_collector = Mock()
        
        # Create test snapshot
        snapshot = ResourceSnapshot(
            node_id="test-node",
            node_name="test-node",
            timestamp=datetime.now(UTC),
            cpu_count=8,
            cpu_used=4,
            cpu_available=4,
            cpu_percent=50.0,
            memory_total=32 * 1024**3,
            memory_used=16 * 1024**3,
            memory_available=16 * 1024**3,
            memory_percent=50.0,
            gpu_count=1,
            gpu_used=0,
            gpu_available=1,
            gpu_memory_total=16 * 1024**3,
            gpu_memory_used=0,
            gpu_memory_available=16 * 1024**3,
        )
        
        orchestrator.metrics_collector.get_all_latest_snapshots.return_value = {
            "test-node": snapshot,
        }
        
        # Get snapshots
        snapshots = orchestrator.get_node_resource_snapshots()
        
        assert "test-node" in snapshots
        assert snapshots["test-node"]["cpu"]["total"] == 8
        assert snapshots["test-node"]["cpu"]["used"] == 4
        assert snapshots["test-node"]["cpu"]["available"] == 4
        assert snapshots["test-node"]["memory"]["total_gb"] == 32
        assert snapshots["test-node"]["gpu"]["total"] == 1
        assert snapshots["test-node"]["pressure"]["overall"] == 0.5


# Integration Tests
class TestResourceSharingIntegration:
    """Integration tests for the complete resource sharing system."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_resource_sharing(self, cluster_config, mock_ssh_manager):
        """Test end-to-end resource sharing flow."""
        # This test requires actual Ray, so we'll mock it
        with patch('distributed_grid.monitoring.resource_metrics.ray') as mock_ray, \
             patch('distributed_grid.orchestration.resource_sharing_manager.ray') as mock_ray_manager, \
             patch('distributed_grid.orchestration.intelligent_scheduler.ray') as mock_ray_scheduler:
            
            # Setup mocks
            mock_ray.is_initialized.return_value = True
            mock_ray.cluster_resources.return_value = {"CPU": 18, "GPU": 2}
            mock_ray.available_resources.return_value = {"CPU": 9, "GPU": 2}
            mock_ray.nodes.return_value = [
                {"NodeManagerAddress": "localhost", "Resources": {"CPU": 8, "GPU": 1}},
                {"NodeManagerAddress": "worker1", "Resources": {"CPU": 6, "GPU": 1}},
                {"NodeManagerAddress": "worker2", "Resources": {"CPU": 4, "GPU": 0}},
            ]
            
            mock_ray_manager.util.placement_group.return_value = Mock()
            mock_ray_manager.get.return_value = True
            
            # Create orchestrator
            orchestrator = ResourceSharingOrchestrator(
                cluster_config,
                mock_ssh_manager,
            )
            
            try:
                # Initialize
                await orchestrator.initialize()
                await orchestrator.start()
                
                # Get initial status
                status = await orchestrator.get_cluster_status()
                assert status["resource_sharing_enabled"] is True
                
                # Request resources
                request_id = await orchestrator.request_resources(
                    node_id="test-master",
                    resource_type="cpu",
                    amount=2.0,
                )
                assert request_id is not None
                
                # Get node snapshots
                snapshots = orchestrator.get_node_resource_snapshots()
                assert len(snapshots) == 3
                
            finally:
                await orchestrator.stop()


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
