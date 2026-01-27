from distributed_grid.orchestration.offloading_service import OffloadingService


def test_offloading_service_blocks_head_target(sample_cluster_config):
    service = OffloadingService(sample_cluster_config)
    head_name = sample_cluster_config.nodes[0].name
    assert service._is_worker_target(head_name) is False


def test_auto_offload_sets_state(sample_cluster_config):
    service = OffloadingService(sample_cluster_config)
    service.auto_enable(interval=5, thresholds={"cpu": 0.8})
    assert service.state.enabled is True
