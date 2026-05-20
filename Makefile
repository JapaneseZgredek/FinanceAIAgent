.DEFAULT_GOAL := help
PYTHON := python3

# ---------------------------------------------------------------------------
# Variables (user-supplied via `make target VAR=val`)
# ---------------------------------------------------------------------------
SYMBOL  ?=
REPORT  ?=
DATE    ?=

# Guard: error out when a required variable is empty
guard-%:
	@if [ -z '$(${*})' ]; then \
		echo "Error: $* is required. Usage: make <target> $*=<value>"; \
		exit 1; \
	fi

# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------

.PHONY: help install install-lock install-dev run lint format report compare export charts clean env-check test

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install core dependencies
	pip install -r requirements.txt

install-lock: ## Install pinned dependencies
	pip install -r requirements.lock.txt

install-dev: ## Install dev tools (ruff)
	pip install ruff

run: ## Launch interactive mode
	$(PYTHON) main.py

lint: ## Check lint + formatting (no changes)
	ruff check .
	ruff format --check .

format: ## Auto-format + auto-fix lint issues
	ruff format .
	ruff check --fix .

report: guard-SYMBOL ## Generate report (SYMBOL=BTC)
	$(PYTHON) main.py analyze --symbol $(SYMBOL)

compare: guard-SYMBOL ## Compare reports (SYMBOL=ETH)
	$(PYTHON) main.py compare --symbol $(SYMBOL)

export: guard-REPORT ## Export report to HTML (REPORT=2026-05-10_BTC)
	$(PYTHON) main.py export --report $(REPORT)

charts: guard-SYMBOL guard-DATE ## Generate charts (SYMBOL=BTC DATE=2026-05-10)
	$(PYTHON) main.py charts --symbol $(SYMBOL) --date $(DATE)

clean: ## Remove caches and Python artifacts
	rm -rf .cache/ .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true

env-check: ## Verify .env and venv are set up
	@if [ -z "$$VIRTUAL_ENV" ]; then \
		echo "Warning: virtual environment not active. Run: source .venv/bin/activate"; \
	else \
		echo "venv: $$VIRTUAL_ENV"; \
	fi
	@if [ ! -f .env ]; then \
		echo "Error: .env not found. Copy .env.example to .env and fill in API keys."; \
		exit 1; \
	else \
		echo ".env: OK"; \
	fi

test: ## Run tests (not yet available — see docs/ROADMAP.md Phase 5)
	@echo "No tests yet — see docs/ROADMAP.md Phase 5 (#24-26)"
