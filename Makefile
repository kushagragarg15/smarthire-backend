.PHONY: help install dev test clean run setup lint format

# Default target
help:
	@echo "SmartHire Development Commands"
	@echo "=============================="
	@echo "install    - Install dependencies"
	@echo "dev        - Install development dependencies"
	@echo "test       - Run tests"
	@echo "run        - Run the application"
	@echo "setup      - Initial setup (create venv, install deps)"
	@echo "clean      - Clean up temporary files"
	@echo "lint       - Run linting"
	@echo "format     - Format code"

# Create virtual environment and install dependencies
setup:
	python3 -m venv venv
	. venv/bin/activate && pip install --upgrade pip
	. venv/bin/activate && pip install -r config/requirements.txt

# Install dependencies
install:
	pip install -r config/requirements.txt

# Install development dependencies
dev: install
	pip install pytest black flake8 mypy

# Run tests
test:
	python -m pytest tests/ -v

# Run the application
run:
	python main.py

# Clean up temporary files
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf build/ dist/

# Run linting
lint:
	flake8 src/ tests/
	mypy src/

# Format code
format:
	black src/ tests/ main.py setup.py
