# Changelog

## [Unreleased]
- **Quality gates:** added a pytest unit suite under `tests/` (config loading,
  validation, URL/LaTeX normalisation, bibtex escaping, repo relevance /
  classification, metadata ID extraction, saturate helpers, and the shared
  HTTP retry helper). Wired into CI via a new `test` job.
- **Freshness gates:** `standard_stats.py` and `analysis/generate_reports.py`
  now support `--check` (exit 1 when outputs are stale), mirroring
  `generate_readme.py --check`. The CI `validate` job now runs all three
  `--check` gates plus `research_config.py` validation.
- **Config validation:** `research_config.validate_config()` / `require_valid_config()`
  fail fast on a malformed `config/taxonomy.yaml` (missing/duplicate categories or
  subcategories, bad id casing, dangling `subcategory_keywords`). All pipeline
  scripts and tools now call it at startup.
- **Shared HTTP/rate-limit handling:** new `repos_common.http_get_with_retry()` +
  `_retry_after_seconds()` centralise the duplicated 429/`Retry-After`/5xx/timeout
  backoff logic. `fetch_codeberg_repos.py` and `fetch_gitlab_repos.py` now use it
  (consistent capped `Retry-After` handling instead of hardcoded 60s waits).
- **Display-name de-duplication:** new `research_config.display_name()` shared by
  report/tool generators so category/subcategory display logic lives in one place.
- **Task runner:** added a root `Makefile` (`make validate`, `make check`,
  `make generate`, `make test`, `make discover`, `make all`).
- **Housekeeping:** `papers.yaml` cleaned of two off-topic, unvalidated leftover
  entries (now validates out of the box); README bootstrap now clones
  `skeleton-research` (not a stale `mobile-apps-best-practices` URL).

## [0.2.0] — 2026-08-07
- **Bug fix:** All arXiv API calls now use `https://` instead of `http://`
  (`fetch_new_papers.py`, `fetch_metadata.py`, `saturate_papers.py`). Many
  networks block plain HTTP; HTTPS is required for arXiv's API.
- **Bug fix:** `fetch_new_papers.py` — fixed `NameError` (`QUERIES` → `queries`) that
  crashed multi-query arXiv discovery runs.
- **Bug fix:** `fetch_openalex_bulk.py` — `reconstruct_abstract()` and
  `sanitize_date()` no longer return the literal string `"papers"` on empty/bad
  input; they return `""` as intended.
- **Config-driven trend keywords:** `standard_stats.py`, `trend_scanner.py`, and
  `landscape_analyzer.py` now read `trend_keywords` from `config/taxonomy.yaml`
  (via `research_config.get_trend_keywords()`), falling back to the built-in list.
  Each repo can now define topic-specific burst keywords.
- **Config-driven subcategory classification:** `fetch_new_papers.py` now exports
  `classify_subcategory(title, abstract, cfg)` that reads `subcategory_keywords`
  from `taxonomy.yaml` first, then falls back to heuristics. `fetch_other_sources.py`
  picks this up automatically via its existing import.
- **Config-driven display names:** `topic_planner.py`, `trend_scanner.py`,
  `landscape_analyzer.py`, `brief_generator.py`, and `standard_stats.py` now use
  `research_config.category_display()` / `subcategory_display()` for proper
  display names instead of raw title-casing of kebab IDs.
- **Config-driven OpenAlex mailto:** `fetch_openalex_bulk.py` reads
  `topic.openalex_mailto` from `taxonomy.yaml` (with env `OPENALEX_MAILTO` override)
  instead of a hardcoded address.
- **`research_config.py`** added `get_trend_keywords()`, `get_subcategory_keywords()`,
  and `get_openalex_mailto()` helpers.

## [0.1.0] — 2026-08-06
- Initial skeleton: config-driven taxonomy, validation, README generation, statistics, reports, discovery, GitHub Pages, CI, AGENTS.md.
