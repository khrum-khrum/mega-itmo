.PHONY: help install lint format run-example clean

include .env

help:
	@echo "Available targets:"
	@echo "  make install      - Install dependencies"
	@echo "  make lint         - Run ruff linter"
	@echo "  make format       - Format code with black and ruff"
	@echo "  make run-example  - Run code agent with issue #2"
	@echo "  make clean        - Remove cache files"

install:
	pip install -r requirements.txt

lint:
	ruff check src/

format:
	black src/
	ruff check --select I --fix src/

run-example:
	python -m src.code_agent.cli \
		--issue 8 \
		--model upstage/solar-pro-3:free \
		--execute \
		-v

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
