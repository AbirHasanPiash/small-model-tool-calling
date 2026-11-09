# The same commands work in every project. Run `make` to list them.
.DEFAULT_GOAL := help
.PHONY: help setup lint fmt test eval check up down keys clean

help: ## List the commands
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  make %-6s %s\n", $$1, $$2}'

setup: ## Install dependencies and the git hooks
	uv sync
	pre-commit install

lint: ## Lint and check formatting (what CI runs)
	uv run ruff check .
	uv run ruff format --check .

fmt: ## Fix what can be fixed, then format
	uv run ruff check --fix .
	uv run ruff format .

test: ## Fast tests: no model calls
	uv run pytest -m "not eval"

eval: ## Eval suite: calls models, uses API quota
	uv run pytest -m eval

check: lint test ## Everything CI checks

up: ## Start local services from compose.yaml
	@if [ -f compose.yaml ]; then docker compose up -d --wait; else echo "No compose.yaml in this project yet."; fi

down: ## Stop local services (data is kept)
	@if [ -f compose.yaml ]; then docker compose down; else echo "No compose.yaml in this project yet."; fi

keys: ## Check API keys and Langfuse tracing
	@test -f .env || { echo "No .env yet. Run: cp .env.example .env, then paste your keys."; exit 1; }
	uv run --env-file .env scripts/check_providers.py $(ARGS)

clean: ## Delete caches (safe: they are rebuilt)
	rm -rf .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
