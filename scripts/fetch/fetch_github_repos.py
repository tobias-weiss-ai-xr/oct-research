#!/usr/bin/env python3
"""Discover GitHub repositories relevant to your research topic.

Reads GitHub search queries from ``config/taxonomy.yaml`` under the
``github_queries`` key.  Each query can optionally specify a category,
subcategory hint, and a minimum-stars override.  Repos are appended to
``repos.yaml`` (sibling to ``papers.yaml``) in the same taxonomy.

GitHub queries use the standard search syntax:
  https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories

Requirements:
  - ``gh`` CLI installed and authenticated (``gh auth status``)
  - ``pip install pyyaml``

Usage:
    python3 scripts/fetch/fetch_github_repos.py --dry-run
    python3 scripts/fetch/fetch_github_repos.py --min-stars 100
    python3 scripts/fetch/fetch_github_repos.py --from 5 --to 10

Output: repos.yaml in the repo root.
"""

import argparse
import json
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

# Allow imports from scripts/ (sibling directory)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import research_config
from repos_common import (
    REPOS_YAML,
    _norm,
    load_topic_signals,
    is_relevant_repo,
    normalize_entry,
    load_existing_repos,
    append_repos,
)


# ── Config loading ────────────────────────────────────────────────────────

def load_github_queries(cfg):
    """Load github_queries from taxonomy.yaml.

    Each entry must have ``query``.  Optional: ``category``,
    ``subcategory_hint``, ``min_stars``.
    """
    queries = []
    for item in cfg.get("github_queries", []):
        q = item.get("query", "")
        if not q:
            continue
        queries.append({
            "query": q,
            "category": item.get("category", ""),
            "subcategory_hint": item.get("subcategory_hint", ""),
            "min_stars": item.get("min_stars"),
        })
    return queries


# ── GitHub API helpers ────────────────────────────────────────────────────

def gh_search_repos(query, sort="stars", order="desc", per_page=30, page=1):
    """Search GitHub repos via ``gh api``.  Returns (items, total_count)."""
    cmd = [
        "gh", "api", "--method", "GET",
        f"search/repositories?q={query}&sort={sort}&order={order}"
        f"&per_page={per_page}&page={page}",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            err = result.stderr.strip()
            if "422" in err or "rate limit" in err.lower():
                return [], 0
            if "could not resolve host" in err.lower():
                print("  WARNING: network error — skipping query", flush=True)
                return [], 0
            print(f"  WARNING: gh api error: {err[:120]}", flush=True)
            return [], 0
        data = json.loads(result.stdout)
        return data.get("items", []), data.get("total_count", 0)
    except subprocess.TimeoutExpired:
        print("  WARNING: gh api timeout (30s)", flush=True)
        return [], 0
    except json.JSONDecodeError:
        return [], 0


def github_to_raw(item):
    """Map a GitHub API search result to a normalised raw dict."""
    return {
        "name": item.get("full_name", ""),
        "url": item.get("html_url", ""),
        "description": item.get("description") or "",
        "stars": item.get("stargazers_count", 0),
        "forks": item.get("forks_count", 0),
        "language": item.get("language") or "",
        "topics": item.get("topics", []),
        "pushed_at": item.get("pushed_at", "")[:10],
        "created_at": item.get("created_at", "")[:10],
        "open_issues": item.get("open_issues_count", 0),
        "license": (item.get("license") or {}).get("spdx_id", ""),
    }


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Discover GitHub repos relevant to your research topic."
    )
    parser.add_argument("--min-stars", type=int, default=50,
                        help="Default minimum star threshold (default: 50)")
    parser.add_argument("--per-page", type=int, default=30,
                        help="Results per GitHub query page (max 100)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without writing files")
    parser.add_argument("--sleep", type=float, default=3.0,
                        help="Seconds between queries (default: 3)")
    parser.add_argument("--max-pages", type=int, default=3,
                        help="Max pages per query (default: 3 = 90 repos/query)")
    parser.add_argument("--from", dest="from_idx", type=int, default=0,
                        help="Start at query index (0-based)")
    parser.add_argument("--to", dest="to_idx", type=int, default=None,
                        help="Stop at query index (inclusive)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output file path (default: repos.yaml)")
    args = parser.parse_args()

    cfg = research_config.require_valid_config()
    queries = load_github_queries(cfg)

    if not queries:
        topic_name = cfg.get("topic", {}).get("name", "your topic")
        print("ERROR: No github_queries defined in config/taxonomy.yaml.", file=sys.stderr)
        print("Add a ``github_queries`` section, e.g.:", file=sys.stderr)
        print("", file=sys.stderr)
        print("github_queries:", file=sys.stderr)
        print(f'  - query: "topic:{_norm(topic_name).replace(" ", "-")}+stars:>50"', file=sys.stderr)
        print('    category: method', file=sys.stderr)
        print('  - query: "YOUR KEYWORD+tool+stars:>100"', file=sys.stderr)
        print('    category: application', file=sys.stderr)
        print("", file=sys.stderr)
        print("See: https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories",
              file=sys.stderr)
        sys.exit(1)

    # Build relevance filter
    signals = load_topic_signals(cfg)
    import repos_common
    signal_re = repos_common._word_re(signals) if signals else re.compile(r"(?!)")
    print(f"Relevance signals: {len(signals)} tokens", flush=True)

    output_path = Path(args.output) if args.output else REPOS_YAML
    topic_short = cfg.get("topic", {}).get("short", "research")

    to_idx = args.to_idx if args.to_idx is not None else len(queries) - 1
    active = queries[args.from_idx:to_idx + 1]

    existing_names, existing_count = load_existing_repos(output_path)
    print(f"Loaded {existing_count} existing repos from {output_path.name}", flush=True)
    print(f"Running {len(active)}/{len(queries)} queries (min-stars {args.min_stars})...", flush=True)

    all_new = []
    total_results = 0
    filtered_out = 0

    for qi, qinfo in enumerate(active, start=args.from_idx):
        query_raw = qinfo["query"]
        cat = qinfo.get("category", "")
        hint = qinfo.get("subcategory_hint", "")
        q_min_stars = qinfo.get("min_stars", args.min_stars)

        if "stars:" not in query_raw:
            query = f"{query_raw}+stars:>{q_min_stars}"
        else:
            query = re.sub(r'stars:>\d+', f'stars:>{q_min_stars}', query_raw)

        label = f"[{cat}]" if cat else f"[q{qi}]"
        print(f"\nQuery {qi + 1}/{len(queries)} {label} {query[:90]}", flush=True)

        for page in range(1, args.max_pages + 1):
            items, total = gh_search_repos(query, per_page=args.per_page, page=page)
            if qi == args.from_idx and page == 1:
                total_results += total
                print(f"  {total} total results", flush=True)

            if not items:
                break

            page_new = 0
            for item in items:
                name = item.get("full_name", "")
                if name.lower().strip() in existing_names:
                    continue

                desc = item.get("description") or ""
                topics = item.get("topics", [])

                if not is_relevant_repo(name, desc, topics, signal_re):
                    filtered_out += 1
                    continue

                existing_names.add(name.lower().strip())
                raw = github_to_raw(item)
                entry = normalize_entry(raw, cat, hint, cfg)
                all_new.append(entry)
                page_new += 1

            print(f"  page {page}: {len(items)} results, {page_new} new, "
                  f"{len(items) - page_new} dup/filtered", flush=True)

            if len(items) < args.per_page:
                break

        time.sleep(args.sleep)

    print(f"\n{'='*60}", flush=True)
    print(f"Total search results scanned: {total_results}", flush=True)
    print(f"Filtered out (irrelevant): {filtered_out}", flush=True)
    print(f"New relevant repos: {len(all_new)}", flush=True)

    if not all_new:
        print("No new repos to add.", flush=True)
        return

    if args.dry_run:
        print(f"\n--- Candidate repos (first 20) ---", flush=True)
        for e in sorted(all_new, key=lambda x: x["stars"], reverse=True)[:20]:
            print(f"  [{e['category']}/{e['subcategory']}] "
                  f"⭐{e['stars']:>5} {e['name']}", flush=True)
            if e.get("description"):
                print(f"    {e['description'][:100]}", flush=True)
        remaining = max(0, len(all_new) - 20)
        if remaining:
            print(f"... and {remaining} more", flush=True)
        print("\nDry run complete — no files modified.", flush=True)
        return

    append_repos(output_path, all_new, topic_short)
    print(f"\nAppended {len(all_new)} repos to {output_path.name}", flush=True)

    cats = Counter(e["category"] for e in all_new)
    langs = Counter(e["language"] for e in all_new if e["language"])
    total_stars = sum(e["stars"] for e in all_new)

    print("\nCategory breakdown:", flush=True)
    for c, count in cats.most_common():
        print(f"  {c:20} {count:4}", flush=True)

    print("\nTop languages:", flush=True)
    for lang, count in langs.most_common(5):
        print(f"  {lang:15} {count:4}", flush=True)

    print(f"\nTotal new stars: {total_stars:,}", flush=True)


if __name__ == "__main__":
    main()
