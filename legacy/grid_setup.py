import json
import os
import subprocess
import sys

# --- CONFIGURATION ---
CONFIG = {
    "nodes": ["gpu1", "gpu2"],
    "remote_workspace_root": "~/grid_workspace",
    # Tools you want pre-installed on all workers
    "npm_globals": ["typescript", "nodemon", "yarn"],
    "pip_packages": ["torch", "tensorflow", "numpy", "pandas", "black", "pylint"],
}


class GridSetup:
    def __init__(self):
        self.green = "\033[92m"
        self.reset = "\033[0m"

    def cmd(self, host, command):
        """Runs SSH command on host."""
        print(f"{self.green}[{host}]{self.reset} {command}")
        # -o BatchMode=yes fails quickly if ssh is down
        ssh = f"ssh -o BatchMode=yes {host} '{command}'"
        return subprocess.run(ssh, shell=True)

    def provision_node(self, host):
        print(f"\n--- Provisioning {host} ---")

        # 1. Create Workspace Directory
        self.cmd(host, f"mkdir -p {CONFIG['remote_workspace_root']}")

        # 2. Sync System Dependencies (Ubuntu 24 specific)
        # Note: You need sudo access or passwordless sudo for this part usually.
        # We assume standard user access for now, so we skip apt-get.

        # 3. Setup Python Virtual Environment (The "Global" Grid Env)
        venv_path = f"{CONFIG['remote_workspace_root']}/grid_env"
        self.cmd(host, f"python3 -m venv {venv_path}")

        # 4. Install Common Python Libs
        pip_bin = f"{venv_path}/bin/pip"
        pkgs = " ".join(CONFIG["pip_packages"])
        self.cmd(host, f"{pip_bin} install -U pip {pkgs}")

        # 5. Check Node Version & Install Globals
        # We assume Node is installed, but we install global tools to user prefix
        npm_pkgs = " ".join(CONFIG["npm_globals"])
        self.cmd(
            host, f"mkdir -p ~/.npm-global && npm config set prefix '~/.npm-global'"
        )
        self.cmd(
            host, f"export PATH=~/.npm-global/bin:$PATH && npm install -g {npm_pkgs}"
        )

    def generate_balancer_config(self):
        """Exports config for the load balancer to use."""
        with open("grid_config.json", "w") as f:
            json.dump(CONFIG, f, indent=2)
        print(f"\n{self.green}Configuration saved to grid_config.json{self.reset}")


if __name__ == "__main__":
    setup = GridSetup()
    setup.generate_balancer_config()

    print("Starting Grid Provisioning...")
    for node in CONFIG["nodes"]:
        setup.provision_node(node)

    print("\nSystem Ready. Please copy 'drun' to your local /usr/local/bin.")
