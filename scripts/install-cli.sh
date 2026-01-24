#!/bin/bash
# System-wide CLI installation script for distributed-grid

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🚀 Installing grid CLI system-wide..."
echo ""

cd "$PROJECT_ROOT"

# Check if Poetry is installed
if ! command -v poetry >/dev/null 2>&1; then
    echo "❌ Poetry is not installed."
    echo "   Install Poetry: https://python-poetry.org/docs/#installation"
    exit 1
fi

# Check if Poetry environment exists, if not install dependencies
if ! poetry env info >/dev/null 2>&1; then
    echo "📦 Installing dependencies with Poetry..."
    poetry install
fi

# Get Poetry virtual environment path
POETRY_VENV=$(poetry env info --path)

if [ -z "$POETRY_VENV" ]; then
    echo "❌ Error: Could not find Poetry virtual environment"
    exit 1
fi

# Create ~/.local/bin if it doesn't exist
mkdir -p ~/.local/bin

# Create symlink
if [ -f "$POETRY_VENV/bin/grid" ]; then
    ln -sf "$POETRY_VENV/bin/grid" ~/.local/bin/grid
    echo "✅ Symlink created: ~/.local/bin/grid -> $POETRY_VENV/bin/grid"
else
    echo "⚠️  grid command not found in Poetry environment, trying pip install..."
    pip install --user --editable . || {
        echo "❌ Installation failed"
        exit 1
    }
fi

# Check if ~/.local/bin is in PATH
if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
    echo ""
    echo "⚠️  Warning: ~/.local/bin is not in your PATH"
    echo ""
    echo "Add this to your shell configuration:"
    
    if [ -f ~/.bashrc ]; then
        echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
        echo "  source ~/.bashrc"
    elif [ -f ~/.zshrc ]; then
        echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc"
        echo "  source ~/.zshrc"
    else
        echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    fi
    echo ""
fi

# Verify installation
echo ""
echo "🔍 Verifying installation..."
if command -v grid >/dev/null 2>&1; then
    echo "✅ grid CLI is installed and available!"
    echo ""
    echo "Location: $(which grid)"
    echo "Test it: grid --help"
else
    echo "⚠️  grid command not found in PATH"
    echo "   Make sure ~/.local/bin is in your PATH and reload your shell"
fi

echo ""
echo "✨ Installation complete!"
echo ""
echo "Next steps:"
echo "  1. Run 'grid --help' to see available commands"
echo "  2. Run 'grid init' to create a cluster configuration"
echo "  3. See docs/cli_system_wide_setup.md for more details"
