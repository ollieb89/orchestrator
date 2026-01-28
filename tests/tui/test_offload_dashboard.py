from types import SimpleNamespace

from distributed_grid.tui.offload_dashboard import OffloadDashboard


class FakeSnapshot(SimpleNamespace):
    pass


def test_dashboard_updates_from_snapshot(sample_cluster_config):
    state = SimpleNamespace(enabled=False, active_offloads=[], recent_events=[])
    head = SimpleNamespace(cpu_percent=42.0, memory_percent=55.0, gpu_pressure=0.25)
    nodes = {
        "worker1": SimpleNamespace(
            cpu_percent=10.0,
            memory_percent=20.0,
            gpu_pressure=0.1,
            overall_pressure=0.3,
        )
    }
    snapshot = FakeSnapshot(head=head, nodes=nodes)

    dash = OffloadDashboard(state=state)
    dash.update_from_snapshot(snapshot)

    assert dash._head_metrics["cpu"] == 42.0
    assert dash._worker_metrics[0]["name"] == "worker1"
