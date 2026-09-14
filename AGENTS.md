# AGENTS.md — Agentic Workflow for This Research Corpus

> Read this first. It tells coding agents how to work safely in this repo.

## Project purpose

Data-driven, auto-validated literature review corpus. The repo is a **skeleton**
for a research topic: papers live in `papers.yaml`, everything else is generated.

## Non-negotiable rules

1. **Never edit the generated `README.md` sections by hand.** The paper list
   and the corpus-statistics block are owned by the pipeline and delimited by
   invisible HTML-comment markers
   (`<!-- BEGIN PAPER LIST -->` / `<!-- BEGIN CORPUS STATISTICS -->` …
   `<!-- END … -->`). `scripts/generate_readme.py` regenerates the paper
   list; `scripts/standard_stats.py` regenerates the corpus statistics. Any
   other README prose is user-owned and left untouched. Edit `papers.yaml`,
   then regenerate.
2. **Never edit `docs/papers.json`, `statistics.json`, or `docs/research/*.md`
   by hand.** They are pipeline outputs.
3. **Never invent papers.** Every entry in `papers.yaml` must have a real,
   verifiable `url`. If you cannot verify a paper exists, do not add it.
4. **After any `papers.yaml` change, run the full pipeline** and make sure it
   passes before considering the task done:
   ```bash
   python3 scripts/validate_papers.py && \
   python3 scripts/generate_readme.py && \
   python3 scripts/standard_stats.py && \
   python3 scripts/analysis/generate_reports.py
   ```
   (Equivalently: `make all`, which also runs tests and freshness checks.)
5. **Validate before committing:** `python3 scripts/validate_papers.py` must
   exit 0. Fix errors (schema, duplicates, URL normalization) — do not
   bypass validation.
6. **Run the unit tests before committing:** `python3 -m pytest` must pass.
   If you touched pipeline *scripts* (not just data), add/adjust tests under
   `tests/` for any pure functions you changed.
7. **If you added a script**, document it in the README's discovery/utility
   table and this structure block; give it an argparse CLI and pass
   `config/taxonomy.yaml` through `research_config`.

## Adding a paper (agent checklist)

1. Search `papers.yaml` for duplicates by title AND by arXiv id/URL.
2. Fetch the real metadata (title, authors, date, abstract, venue) from
   arXiv/Semantic Scholar/OpenAlex — do not guess.
3. Assign `category` and `subcategory` using ONLY the values defined in
   `config/taxonomy.yaml`. If no existing cell fits, do not invent a new one;
   note it and ask.
4. Use normalized arXiv URLs: `https://arxiv.org/abs/XXXX.XXXXX`
   (no `pdf`, no `doi.org/10.48550`, no `www.`).
5. Run the pipeline (rule 4), commit, done.

## Project structure

```
config/taxonomy.yaml          ← THE config: topic, taxonomy, queries (edit me)
papers.yaml                   ← source of truth (edit me to add papers)
scripts/research_config.py    ← single config loader (all scripts use this)
scripts/readme_sections.py    ← marker-delimited README sections owned by the pipeline
scripts/validate_papers.py    ← schema/duplicate/URL validation
scripts/generate_readme.py    ← README.md paper list + docs/papers.json from papers.yaml
scripts/standard_stats.py     ← statistics.json + papers.json + graph data + README corpus statistics
scripts/analysis/generate_reports.py → docs/research/{literature_review,trends}.md
scripts/fetch/                ← arXiv/OpenAlex/dblp/crossref/europepmc/GitHub/GitLab/Codeberg discovery
scripts/fetch/repos_common.py ← shared repo-fetcher logic (HTTP retry, relevance)
tests/                        ← pytest unit suite (`python3 -m pytest`)
Makefile                      ← task runner: `make validate|check|generate|test|all`
tools/                        ← topic_planner, trend_scanner, landscape_analyzer, brief_generator
docs/index.html               ← GitHub Pages paper browser (reads docs/papers.json)
```

## Freshness gates (`--check`)

`generate_readme.py`, `standard_stats.py`, and `analysis/generate_reports.py`
all support a non-destructive `--check` mode (exit 1 if output is stale) used
by CI and `make check`. Run them after touching data or category scripts.

## Common agent tasks

- **"Add this paper"** → follow the checklist above.
- **"What are the hottest topics?"** → `python3 tools/trend_scanner.py --months 12`
- **"What are the research gaps?"** → `python3 tools/landscape_analyzer.py`
- **"Suggest article topics"** → `python3 tools/topic_planner.py --top 10`
- **"Find new papers"** → `python3 scripts/fetch/fetch_new_papers.py --local` (needs network)
- **"Find GitHub repos"** → add ``github_queries`` to ``config/taxonomy.yaml``, then `python3 scripts/fetch/fetch_github_repos.py --dry-run`
- **"Find GitLab projects"** → add ``gitlab_queries`` to ``config/taxonomy.yaml``, then `python3 scripts/fetch/fetch_gitlab_repos.py --dry-run`
- **"Find Codeberg repos"** → add ``codeberg_queries`` to ``config/taxonomy.yaml``, then `python3 scripts/fetch/fetch_codeberg_repos.py --dry-run`
- **"Fix broken/duplicate entries"** → validate with `--fix`, then review
  changed entries manually.
