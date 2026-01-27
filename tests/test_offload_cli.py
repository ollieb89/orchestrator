from click.testing import CliRunner

import distributed_grid.cli as cli_module


class DummyOffloadingService:
    def __init__(self, cluster_config, ssh_manager=None):
        self.cluster_config = cluster_config

    async def execute(
        self,
        pid,
        target_node=None,
        capture_state=True,
        runtime_env=None,
        ray_dashboard="http://localhost:8265",
    ):
        return "task-123"

    def get_task_status(self, task_id):
        return None

    async def shutdown(self):
        return None


def test_offload_execute_prompts_for_pid(sample_cluster_config, monkeypatch):
    monkeypatch.setattr(cli_module, "OffloadingService", DummyOffloadingService)
    monkeypatch.setattr(cli_module.ClusterConfig, "from_yaml", lambda _path: sample_cluster_config)

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cli,
        ["offload", "execute", "-c", "config/my-cluster.yaml"],
        input="123\n",
    )
    assert result.exit_code == 0
    assert "Offloading process 123" in result.output
