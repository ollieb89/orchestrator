from distributed_grid.orchestration.offloading_service import OffloadingService


def test_offloading_service_blocks_head_target(sample_cluster_config):
    service = OffloadingService(sample_cluster_config)
    head_name = sample_cluster_config.nodes[0].name
    assert service._is_worker_target(head_name) is False
