# 3-PC GPU Cluster Setup

## Cluster Configuration
- **Nodes**: 3 PCs configured as Ray cluster
- **gpu-master** (192.168.1.100): Head node, user: ollie, 1 GPU
- **gpu1** (192.168.1.101): Worker node, user: ob, 1 GPU  
- **gpu2** (192.168.1.102): Worker node, user: ollie, 1 GPU (named ml-server)

## Setup Steps Completed
1. Created `/config/my-cluster.yaml` with node definitions
2. Created `/config/hosts` with IP mappings
3. Installed Ray 2.53.0 on all nodes in `~/distributed_cluster_env`
4. Started Ray cluster successfully

## Key Commands
- **Start cluster**: `poetry run python -m distributed_grid.cli cluster start -c config/my-cluster.yaml`
- **Stop cluster**: `poetry run python -m distributed_grid.cli cluster stop -c config/my-cluster.yaml`
- **Check status**: `poetry run python -m distributed_grid.cli cluster status -c config/my-cluster.yaml`

## Access Information
- **Ray Dashboard**: http://localhost:8265
- **Redis Port**: 6379
- **SSH**: All nodes accessible with verified keys

## Configuration Files
- Main config: `/config/my-cluster.yaml`
- Host mappings: `/config/hosts`

## Notes
- All nodes have Ray installed in `~/distributed_cluster_env`
- Usernames differ: gpu-master/gpu2 use "ollie", gpu1 uses "ob"
- Each node configured with 1 GPU (updated from initial 4 GPUs)
- Cluster successfully started and all nodes connected