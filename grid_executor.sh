#!/bin/bash

# GridRunner - Distributed Execution Wrapper
# Usage: drun [-p PORT] "command to run"

PORT_FORWARD=""
CONFIG_FILE="grid_config.json"
REMOTE_ROOT="~/grid_workspace"

# 1. Parse Arguments (Port forwarding support)
while getopts "p:" opt; do
  case $opt in
    p)
      PORT_FORWARD="-L $OPTARG:localhost:$OPTARG"
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
BEST_NODE=$(python3 grid_balancer.py)

if [ $? -ne 0 ] || [ -z "$BEST_NODE" ]; then
    echo "Error: No available nodes found."
    exit 1
fi

echo -e "\033[92m[GridRunner] Selected: $BEST_NODE\033[0m"

# 3. Project Sync Logic
# We get the current folder name to create a matching folder on remote
CURRENT_DIR_NAME=$(basename "$PWD")
REMOTE_PATH="$REMOTE_ROOT/$CURRENT_DIR_NAME"

echo -e "\033[94m[GridRunner] Syncing context to $BEST_NODE...\033[0m"

# We use rsync to push code.
# EXCLUSIONS are critical to speed. We do NOT sync node_modules or venv usually,
# allowing the remote to handle its own dependencies, OR we sync them if we want exact state.
# For "Heavy IDE" usage, syncing node_modules is slow but safest for consistency.
# Here we exclude .git and heavy build folders.
rsync -azP \
    --exclude '.git' \
    --exclude '__pycache__' \
    --exclude '.env' \
    . $BEST_NODE:$REMOTE_PATH

# 4. Execute
# We activate the grid environment (Python) before running the command.
# We also ensure the PATH includes global npm modules.
echo -e "\033[94m[GridRunner] Executing...\033[0m"

ssh -t $PORT_FORWARD $BEST_NODE "
    export PATH=~/.npm-global/bin:\$PATH;
    source $REMOTE_ROOT/grid_env/bin/activate;
    cd $REMOTE_PATH;
    echo '--- Remote Output ---';
    $CMD
"

# 5. Sync Back (Optional - primarily for generated artifacts)
# Uncomment if your script produces files you need back locally
# rsync -azP $BEST_NODE:$REMOTE_PATH/ .
