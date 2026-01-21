#!/bin/bash

# GridRunner - Distributed Execution Wrapper
# Usage: drun [-p PORT] "command to run"

PORT_FORWARD=""
PORT=""
CONFIG_FILE="grid_config.json"
REMOTE_ROOT="~/grid_workspace"
EXECUTOR="$(dirname "$0")/cluster/executor_optimized.py"

# 1. Parse Arguments (Port forwarding support)
while getopts "p:" opt; do
  case $opt in
    p)
      PORT_FORWARD="-L $OPTARG:localhost:$OPTARG"
      PORT="$OPTARG"
      ;;
    \?)
      echo "Invalid option: -$OPTARG" >&2
      exit 1
      ;;
  esac
done
shift $((OPTIND-1))

CMD="$@"

if [ -z "$CMD" ]; then
    echo "Usage: drun [-p 3000] 'npm start' or 'python script.py'"
    exit 1
fi

# 2. Find the best node
echo -e "\033[94m[GridRunner] Finding best node...\033[0m"
if [ ! -f "$EXECUTOR" ]; then
    echo "Error: optimized executor not found at $EXECUTOR"
    exit 1
fi

echo -e "\033[94m[GridRunner] Executing via optimized executor...\033[0m"

if [ -n "$PORT_FORWARD" ]; then
    python3 "$EXECUTOR" -p "$PORT" $CMD
else
    python3 "$EXECUTOR" $CMD
fi

# 5. Sync Back (Optional - primarily for generated artifacts)
# Uncomment if your script produces files you need back locally
# rsync -azP $BEST_NODE:$REMOTE_PATH/ .
