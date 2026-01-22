.PHONY: help install dev test lint format clean

help:
	@echo "Grid Cluster Development Commands"
	@echo "================================="
	@echo "make install    - Install dependencies"
	@echo "make dev        - Install dev dependencies"
	@echo "make test       - Run tests"
	@echo "make lint       - Run linters"
	@echo "make format     - Format code"
	@echo "make clean      - Remove build artifacts"

install:
	poetry install

dev:
	poetry install --with dev

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
