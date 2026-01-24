.PHONY: help install dev test lint format clean install-system uninstall-system verify-cli

help:
	@echo "Grid Cluster Development Commands"
	@echo "================================="
	@echo "make install        - Install dependencies"
	@echo "make dev            - Install dev dependencies"
	@echo "make install-system - Install CLI system-wide (to ~/.local/bin)"
	@echo "make uninstall-system - Remove system-wide CLI installation"
	@echo "make verify-cli      - Verify CLI is installed and working"
	@echo "make test            - Run tests"
	@echo "make lint            - Run linters"
	@echo "make format          - Format code"
	@echo "make clean           - Remove build artifacts"

install:
	poetry install

dev:
	poetry install --with dev

install-system: install
	@echo "Installing grid CLI system-wide..."
	@POETRY_VENV=$$(poetry env info --path); \
	if [ -z "$$POETRY_VENV" ]; then \
		echo "Error: Poetry virtual environment not found. Run 'poetry install' first."; \
		exit 1; \
	fi; \
	mkdir -p ~/.local/bin; \
	if [ -f "$$POETRY_VENV/bin/grid" ]; then \
		ln -sf "$$POETRY_VENV/bin/grid" ~/.local/bin/grid; \
		echo "✓ Symlink created: ~/.local/bin/grid -> $$POETRY_VENV/bin/grid"; \
	else \
		echo "Error: grid command not found in Poetry environment."; \
		echo "Trying pip install method..."; \
		pip install --user --editable . || { \
			echo "Error: Installation failed. Please check your Python environment."; \
			exit 1; \
		}; \
	fi; \
	if ! echo "$$PATH" | grep -q "$$HOME/.local/bin"; then \
		echo ""; \
		echo "⚠️  Warning: ~/.local/bin is not in your PATH."; \
		echo "Add this to your ~/.bashrc or ~/.zshrc:"; \
		echo "  export PATH=\"\$$HOME/.local/bin:\$$PATH\""; \
	fi; \
	echo ""; \
	echo "✓ Installation complete! Run 'make verify-cli' to verify."

uninstall-system:
	@echo "Removing system-wide CLI installation..."
	@if [ -L ~/.local/bin/grid ]; then \
		rm ~/.local/bin/grid; \
		echo "✓ Removed ~/.local/bin/grid"; \
	elif [ -f ~/.local/bin/grid ]; then \
		rm ~/.local/bin/grid; \
		echo "✓ Removed ~/.local/bin/grid"; \
	else \
		echo "No installation found at ~/.local/bin/grid"; \
	fi; \
	if command -v pip >/dev/null 2>&1; then \
		pip uninstall -y distributed-grid 2>/dev/null || true; \
	fi; \
	echo "✓ Uninstallation complete"

verify-cli:
	@echo "Verifying CLI installation..."
	@if command -v grid >/dev/null 2>&1; then \
		echo "✓ grid command found at: $$(which grid)"; \
		echo ""; \
		echo "Testing grid command..."; \
		grid --help >/dev/null 2>&1 && echo "✓ grid command is working!" || echo "✗ grid command failed"; \
	else \
		echo "✗ grid command not found in PATH"; \
		echo ""; \
		echo "Troubleshooting:"; \
		echo "  1. Check if ~/.local/bin is in your PATH"; \
		echo "  2. Run 'make install-system' to install"; \
		echo "  3. Add to PATH: export PATH=\"\$$HOME/.local/bin:\$$PATH\""; \
		exit 1; \
	fi

test:
	poetry run pytest -v

lint:
	poetry run ruff check .
	poetry run mypy src

format:
	poetry run ruff format .
	poetry run ruff check . --fix

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov dist build *.egg-info .ruff_cache .mypy_cache
