# System-Wide CLI Installation Guide

This guide provides multiple methods to install the `grid` CLI command system-wide, making it available from any directory without needing to activate a virtual environment or use `poetry run`.

## Prerequisites

- Python 3.11 or higher
- Poetry (for method 1) OR pip (for method 2)
- Write access to system/user Python directories

## Installation Methods

### Method 0: Quick Install Script (Easiest)

The simplest way to install the CLI system-wide:

```bash
cd /home/ollie/Development/Tools/cli_tools/orchestrator
./scripts/install-cli.sh
```

Or using Make:

```bash
make install-system
```

This script will:
- Install dependencies with Poetry
- Create a symlink to `~/.local/bin/grid`
- Verify the installation
- Provide instructions if PATH needs to be updated

### Method 1: Poetry Install (Recommended)

This method installs the package in editable mode using Poetry, which is ideal for development.

#### Step 1: Install Dependencies

```bash
cd /home/ollie/Development/Tools/cli_tools/orchestrator
poetry install
```

This creates a virtual environment and installs all dependencies.

#### Step 2: Install CLI System-Wide

**Option A: Install to User Site (Recommended for Single User)**

```bash
# Get the path to the Poetry virtual environment
POETRY_VENV=$(poetry env info --path)

# Create a symlink to the grid command in ~/.local/bin
mkdir -p ~/.local/bin
ln -sf "$POETRY_VENV/bin/grid" ~/.local/bin/grid

# Ensure ~/.local/bin is in your PATH
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

**Option B: Install Globally (Requires sudo)**

```bash
# Get the path to the Poetry virtual environment
POETRY_VENV=$(poetry env info --path)

# Create symlink in system-wide location
sudo ln -sf "$POETRY_VENV/bin/grid" /usr/local/bin/grid
```

**Option C: Use Poetry's Built-in Script Installation**

```bash
# Install the package in editable mode to user site
poetry install --no-root
poetry build
pip install --user --editable .
```

### Method 2: Pip Install (Alternative)

This method uses pip directly, which is simpler but doesn't use Poetry's dependency management.

#### Step 1: Install in Editable Mode

```bash
cd /home/ollie/Development/Tools/cli_tools/orchestrator

# Install in editable mode to user site
pip install --user --editable .

# Or install globally (requires sudo)
sudo pip install --editable .
```

#### Step 2: Verify Installation

```bash
# Check if grid command is available
which grid
grid --help
```

### Method 3: Development Installation with Make

Use the provided Makefile target for easy installation:

```bash
make install-system
```

This will:
1. Install dependencies with Poetry
2. Create a symlink to `~/.local/bin/grid`
3. Verify the installation

You can also use the installation script directly:

```bash
./scripts/install-cli.sh
```

## Verification

After installation, verify the CLI is working:

```bash
# Check if command is available
which grid

# Test the CLI
grid --help

# Test a command
grid status --help
```

## Troubleshooting

### Command Not Found

If `grid` command is not found after installation:

1. **Check PATH**: Ensure `~/.local/bin` is in your PATH
   ```bash
   echo $PATH | grep -q "$HOME/.local/bin" || echo "Not in PATH"
   ```

2. **Add to PATH**: Add to your shell configuration
   ```bash
   # For bash
   echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
   source ~/.bashrc
   
   # For zsh
   echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
   source ~/.zshrc
   ```

3. **Verify symlink**: Check if the symlink exists
   ```bash
   ls -la ~/.local/bin/grid
   ```

### Permission Errors

If you encounter permission errors:

1. **Use user installation**: Use `--user` flag with pip or install to `~/.local/bin`
2. **Check permissions**: Ensure you have write access to the target directory
3. **Use sudo**: For system-wide installation, use `sudo` (not recommended for development)

### Virtual Environment Conflicts

If you have multiple Python environments:

1. **Use Poetry**: Poetry manages virtual environments automatically
2. **Check active environment**: Ensure you're using the correct Python
   ```bash
   which python
   poetry env info
   ```

## Updating the Installation

When you update the code:

```bash
# If using Poetry
poetry install

# If using pip
pip install --user --upgrade --editable .
```

## Uninstallation

To remove the system-wide installation:

```bash
# Remove symlink
rm ~/.local/bin/grid  # or sudo rm /usr/local/bin/grid

# Uninstall package (if installed with pip)
pip uninstall distributed-grid
```

## Best Practices

1. **Development**: Use Poetry with editable install (`poetry install`)
2. **User Installation**: Install to `~/.local/bin` to avoid permission issues
3. **Production**: Consider using a proper package manager or containerization
4. **Version Management**: Use Poetry's version management for consistent environments

## Next Steps

After installation:

1. **Configure**: Set up your cluster configuration
   ```bash
   grid init --config config/my-cluster.yaml
   ```

2. **Test**: Verify cluster connectivity
   ```bash
   grid status --config config/my-cluster.yaml
   ```

3. **Read Documentation**: See `README.md` for usage examples
