import json
import re
import subprocess
import sys
from core.health_check import HealthChecker


def get_config():
    try:
        with open("grid_config.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print("Error: grid_config.json not found. Run grid_setup.py first.")
        sys.exit(1)


def check_node_health(host):
    """
    Returns a score (lower is better).
    Score based on: CPU Load (0-100) + (100 - Free GPU VRAM %)
    """
    try:
        # Get CPU Load (Last 1 minute)
        # and simple GPU check if nvidia-smi exists
        cmd = (
            "cat /proc/loadavg | awk '{print $1}' && "
            "if command -v nvidia-smi &> /dev/null; then "
            "nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits; "
            "else echo '0,0'; fi"
        )

        result = subprocess.run(
            f'ssh -o ConnectTimeout=2 {host} "{cmd}"',
            shell=True,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return 9999  # Node unreachable

        lines = result.stdout.strip().split("\n")
        load_avg = float(lines[0])

        # GPU calculation
        gpu_lines = lines[1:]
        gpu_score = 0
        if gpu_lines and gpu_lines[0].strip() != "0,0":
            used, total = map(int, gpu_lines[0].split(","))
            if total > 0:
                # Percentage of memory used
                gpu_score = (used / total) * 100

        # Weighted Score: We care more about GPU availability for heavy tasks
        # Score = CPU_Load * 10 + GPU_Usage_Percent
        score = (load_avg * 10) + gpu_score
        return score

    except Exception:
        return 9999


def find_best_node():
    config = get_config()
    nodes = config["nodes"]

    checker = HealthChecker(timeout=3, cpu_weight=10.0, gpu_weight=1.0)
    healths = checker.check_all_nodes(nodes, max_workers=min(20, len(nodes)))

    healthy = [h for h in healths if h.is_healthy]
    if healthy:
        return healthy[0].host
    if healths:
        return healths[0].host
    return None


if __name__ == "__main__":
    winner = find_best_node()
    if winner:
        print(winner)
    else:
        sys.exit(1)
