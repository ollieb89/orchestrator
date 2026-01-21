import argparse
import re
import subprocess
import sys
import time

# --- CONFIGURATION ---
# The hostname of your local machine is assumed to be the 'head' node.
WORKER_NODES = ["gpu1", "gpu2"]
# Directory for the dedicated virtual environment on all machines
VENV_PATH = "~/distributed_cluster_env"
PYTHON_BIN = f"{VENV_PATH}/bin/python"
RAY_BIN = f"{VENV_PATH}/bin/ray"


class ClusterManager:
    def __init__(self):
        self.red = "\033[91m"
        self.green = "\033[92m"
        self.reset = "\033[0m"

    def run_local(self, cmd):
        """Runs a command locally."""
        print(f"[{self.green}LOCAL{self.reset}] Executing: {cmd}")
        return subprocess.run(cmd, shell=True, executable="/bin/bash")

    def run_remote(self, host, cmd):
        """Runs a command on a remote host via SSH."""
        print(f"[{self.green}{host}{self.reset}] Executing: {cmd}")
        ssh_cmd = f"ssh {host} '{cmd}'"
        return subprocess.run(ssh_cmd, shell=True, executable="/bin/bash")

    def install(self):
        """Installs Python venv and Ray on all machines."""
        print(f"{self.green}>>> Setting up environments on all nodes...{self.reset}")

        setup_cmd = (
            f"python3 -m venv {VENV_PATH} && "
            f"{VENV_PATH}/bin/pip install -U 'ray[default]' torch numpy"
        )

        # 1. Setup Local
        if self.run_local(setup_cmd).returncode != 0:
            print(f"{self.red}Failed to setup local machine.{self.reset}")
            sys.exit(1)

        # 2. Setup Remotes
        for host in WORKER_NODES:
            if self.run_remote(host, setup_cmd).returncode != 0:
                print(
                    f"{self.red}Failed to setup {host}. Ensure SSH keys are active.{self.reset}"
                )

        print(f"{self.green}>>> Installation complete.{self.reset}")

    def start(self):
        """Starts the Ray cluster."""
        print(f"{self.green}>>> Starting Cluster...{self.reset}")

        # 1. Start Head Node (Local)
        # We bind to 0.0.0.0 so external nodes can connect
        print("Starting Head Node...")
        proc = subprocess.run(
            f"{RAY_BIN} start --head --port=6379 --dashboard-host=0.0.0.0 --include-dashboard=true",
            shell=True,
            capture_output=True,
            text=True,
        )

        if proc.returncode != 0:
            print(
                f"{self.red}Failed to start head node. Is Ray already running?{self.reset}"
            )
            print(proc.stderr)
            return

        # 2. Get the address to join
        # We need the local LAN IP, not localhost
        import socket

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()

        redis_address = f"{local_ip}:6379"
        print(f"Head node is up at {self.green}{redis_address}{self.reset}")

        # 3. Start Worker Nodes
        join_cmd = f"{RAY_BIN} start --address='{redis_address}'"

        for host in WORKER_NODES:
            print(f"Connecting {host}...")
            # We use nohup to ensure it stays running after SSH disconnects, though Ray handles daemonizing usually
            self.run_remote(host, join_cmd)

        print(
            f"\n{self.green}Cluster Active! Access Dashboard at: http://localhost:8265{self.reset}"
        )

    def stop(self):
        """Stops the Ray cluster on all nodes."""
        print(f"{self.green}>>> Stopping Cluster...{self.reset}")

        # Stop workers first
        for host in WORKER_NODES:
            self.run_remote(host, f"{RAY_BIN} stop")

        # Stop head
        self.run_local(f"{RAY_BIN} stop")
        print("Cluster stopped.")

    def status(self):
        """Checks cluster status."""
        self.run_local(f"{RAY_BIN} status")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage a distributed GPU cluster.")
    parser.add_argument(
        "action",
        choices=["install", "start", "stop", "status"],
        help="Action to perform",
    )
    args = parser.parse_args()

    manager = ClusterManager()

    if args.action == "install":
        manager.install()
    elif args.action == "start":
        manager.start()
    elif args.action == "stop":
        manager.stop()
    elif args.action == "status":
        manager.status()
