# Contributing to this Research Corpus

Thank you for contributing! This repo maintains a **data-driven, auto-validated
literature list** for a research topic. The source of truth is `papers.yaml`;
the `README.md` is **auto-generated** — never edit it directly.

## Quick Start: Adding a Paper

1. **Check for duplicates** — search `papers.yaml` by title and URL.
2. **Edit `papers.yaml`** — add your entry following the schema below.
3. **Validate** — run `python3 scripts/validate_papers.py`
4. **Regenerate README** — run `python3 scripts/generate_readme.py`
5. **Regenerate statistics** — run `python3 scripts/standard_stats.py`
   and `python3 scripts/analysis/generate_reports.py`
6. **Commit and open a PR** — CI runs the same checks automatically.

## papers.yaml Schema

```yaml
papers:
  - title: "Paper Title"               # Required
    date: "2026-01"                    # Required, YYYY-MM
    url: "https://arxiv.org/abs/XXXX"  # Required, normalized
    category: "method"                 # Required — see config/taxonomy.yaml
    subcategory: "agentic"             # Required — see config/taxonomy.yaml
    # Optional:
    authors: ["Author1", "Author2"]
    venue: "NeurIPS 2025"
    code_url: "https://github.com/..."
    project_url: "https://..."
    abstract: "..."
    tags: ["tag1", "tag2"]
```

> **Taxonomy:** Allowed values for `category`/`subcategory` are defined in
> `config/taxonomy.yaml`. If a paper does not fit any existing cell, propose
> a taxonomy change in the same PR (config + papers) rather than inventing an
> ad-hoc value.

## URL Normalization Rules

- **arXiv papers**: always use `https://arxiv.org/abs/XXXX`
  - Do NOT use `https://doi.org/10.48550/arXiv.XXXX`
  - Do NOT use `https://www.arxiv.org/abs/XXXX`
  - Do NOT use `https://arxiv.org/pdf/XXXX`
- **Non-arXiv papers**: keep URLs as-is (e.g., `aclanthology.org`,
  `openreview.net`, `papers.nips.cc`).

## Deduplication Checklist

Before adding a paper, verify it is not already in the list under another
category/subcategory (same title or same arXiv ID). The validator flags exact
(title, category, subcategory) duplicates; semantically duplicated entries
still need human judgment.

## PR Checklist

- [ ] Entry has all required fields and valid `category`/`subcategory`
- [ ] URL is normalized (arXiv → `arxiv.org/abs/...`)
- [ ] `python3 scripts/validate_papers.py` exits 0
- [ ] `python3 scripts/generate_readme.py` regenerated README.md
- [ ] `python3 scripts/standard_stats.py` regenerated statistics.json
- [ ] No unrelated changes in the PR
