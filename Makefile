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
	pip install -e .

dev:
	pip install -e '.[dev]'

test:
	pytest -v --cov=grid --cov-report=html

lint:
	ruff check .
	mypy grid

format:
	black .
	isort .

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov dist build *.egg-info
