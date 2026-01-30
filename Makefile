.PHONY: help install lint format run-example run-review-example clean

include .env

help:
	@echo "Available targets:"
	@echo "  make install             - Install dependencies"
	@echo "  make lint                - Run ruff linter"
	@echo "  make format              - Format code with black and ruff"
	@echo "  make run-example         - Run code agent with issue #10"
	@echo "  make run-review-example  - Run review agent with PR (set REPO and PR vars)"
	@echo "  make clean               - Remove cache files"

install:
	pip install -r requirements.txt

lint:
	ruff check src/

format:
	black src/
	ruff check --select I --fix src/

run-example:
	python -m src.code_agent.cli \
		--issue 10 \
		--model upstage/solar-pro-3:free \
		--execute \
		-v

run-review-example:
	@if [ -z "$(REPO)" ] || [ -z "$(PR)" ]; then \
		echo "Error: REPO and PR variables are required"; \
		echo "Usage: make run-review-example REPO=owner/repo PR=123"; \
		exit 1; \
	fi
	python -m src.review_agent.cli \
		--repo $(REPO) \
		--pr $(PR) \
		--model arcee-ai/trinity-large-preview:free \
		--verbose

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
