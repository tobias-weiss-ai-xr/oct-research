# Research Corpus Skeleton — task runner
#
# Convenience wrapper around the raw scripts/commands. Every target is
# idempotent and safe to re-run.
#
# Usage:
#   make validate     # validate config + papers.yaml
#   make check        # fail if generated outputs are stale (CI gate)
#   make generate     # regenerate all derived outputs (README, stats, reports)
#   make test         # run the pytest unit suite
#   make discover     # fetch new arXiv papers & open a PR (needs GH_TOKEN)
#   make help         # list targets
#
# Note: on Windows use `make` from MSYS2/Git-Bash/WSL; commands are sh-compatible.

PY      ?= python3
REPO    := $(CURDIR)

.PHONY: help validate check generate test discover digest all

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

validate: ## Validate config + papers.yaml
	$(PY) scripts/research_config.py
	$(PY) scripts/validate_papers.py

check: ## Fail if any generated output is stale (CI gate)
	$(PY) scripts/generate_readme.py --check
	$(PY) scripts/standard_stats.py --check
	$(PY) scripts/analysis/generate_reports.py --check

generate: ## Regenerate all derived outputs
	$(PY) scripts/generate_readme.py
	$(PY) scripts/standard_stats.py
	$(PY) scripts/analysis/generate_reports.py
	$(PY) scripts/export_bibtex.py

test: ## Run the unit test suite
	$(PY) -m pytest

test-v: ## Run the unit test suite with verbose output
	$(PY) -m pytest -v

test-watch: ## Continuously re-run tests on file changes
	watch -n 2 '$(PY) -m pytest'

discover: ## Fetch new arXiv papers & create a PR (needs GITHUB_TOKEN/GH_TOKEN)
	python3 scripts/fetch/fetch_new_papers.py --months 1 --create-pr

digest: ## Run the news/intelligence ingestion pipeline (writes data/)
	$(PY) run_pipeline.py

digest-dry: ## Dry-run the ingestion pipeline (no writes, no seen)
	$(PY) run_pipeline.py --dry-run

all: validate check generate test ## Run the full local pipeline
