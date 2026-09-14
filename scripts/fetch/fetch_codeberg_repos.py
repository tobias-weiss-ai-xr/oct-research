#!/usr/bin/env python3
"""Discover Codeberg repositories relevant to your research topic.

Reads queries from ``config/taxonomy.yaml`` under the ``codeberg_queries`` key.
Uses the **Codeberg Gitea-compatible API** (no CLI needed).

Codeberg API docs (Gitea-flavoured):
  https://codeberg.org/api/swagger

Requirements:
  - Internet access (public API, no token needed)
  - ``pip install pyyaml requests``

Usage:
    python3 scripts/fetch/fetch_codeberg_repos.py --dry-run
    python3 scripts/fetch/fetch_codeberg_repos.py --min-stars 5
    python3 scripts/fetch/fetch_codeberg_repos.py --host https://codeberg.org

Output: repos.yaml in the repo root (shared with other repo fetchers).
"""

import argparse
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

# Allow imports from scripts/ (sibling directory)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
import research_config
from repos_common import (
    REPOS_YAML,
    _norm,
    load_topic_signals,
    is_relevant_repo,
    normalize_entry,
    load_existing_repos,
    append_repos,
    http_get_with_retry,
    DEFAULT_USER_AGENT,
)

CODEBERG_HOST = os.environ.get("CODEBERG_HOST", "https://codeberg.org")
USER_AGENT = "Research-Corpus/1.0 (mailto:business@tobias-weiss.org)"


# ── Config loading ────────────────────────────────────────────────────────

def load_codeberg_queries(cfg):
    """Load codeberg_queries from taxonomy.yaml.

    Each entry must have ``query``.  Optional: ``category``,
    ``subcategory_hint``, ``min_stars``, ``language``, ``owner`` (restrict
    to a specific org/user).

    Codeberg/Gitea search supports:
      - Plain text search across repo names and descriptions
      - ``topic:TAG`` prefix in query for topic filtering
      - ``language:LANG`` prefix for language filtering
    """
    queries = []
    for item in cfg.get("codeberg_queries", []):
        q = item.get("query", "")
        if not q:
            continue
        queries.append({
            "query": q,
            "category": item.get("category", ""),
            "subcategory_hint": item.get("subcategory_hint", ""),
            "min_stars": item.get("min_stars"),
            "language": item.get("language", ""),
            "owner": item.get("owner", ""),
        })
    return queries


# ── Codeberg / Gitea API helpers ──────────────────────────────────────────

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


def codeberg_search_repos(query, host, per_page=20, page=1, owner=None):
    """Search Codeberg repos via Gitea-compatible API.

    Returns (items, total_count).  The ``repos/search`` endpoint supports
    ``q``, ``sort``, ``order``, ``limit``, ``page``.
    """
    params = {
        "q": query,
        "sort": "stars",
        "order": "desc",
        "limit": min(per_page, 50),  # Gitea max is 50
        "page": page,
    }
    if owner:
        params["q"] = f"{query} user:{owner}"

    resp = http_get_with_retry(
        session, f"{host}/api/v1/repos/search", params=params,
        timeout=30, rate_limit_wait=60,
    )
    if resp is None:
        return [], 0

    if resp.status_code >= 400:
        print(f"  WARNING: Codeberg API {resp.status_code}: {resp.text[:100]}",
              flush=True)
        return [], 0

    try:
        data = resp.json()
    except ValueError:
        return [], 0
    if not isinstance(data, dict):
        return [], 0

    items = data.get("data", [])
    ok = data.get("ok", False)
    total = data.get("total_count", len(items))
    return (items if ok else []), total


def codeberg_to_raw(item):
    """Map a Codeberg/Gitea repo to a normalised raw dict."""
    license_info = item.get("license", {}) or {}
    license_name = ""
    if isinstance(license_info, dict):
        license_name = license_info.get("spdx_id", license_info.get("name", ""))

    topics = item.get("topics", []) or []

    return {
        "name": item.get("full_name", ""),
        "url": item.get("html_url", ""),
        "description": item.get("description") or "",
        "stars": item.get("stargazers_count", 0),
        "forks": item.get("forks_count", 0),
        "language": item.get("language") or "",
        "topics": topics,
        "pushed_at": (item.get("updated_at", "") or "")[:10],
        "created_at": (item.get("created_at", "") or "")[:10],
        "open_issues": item.get("open_issues_count", 0),
        "license": license_name,
    }


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Discover Codeberg repos relevant to your research topic."
    )
    parser.add_argument("--min-stars", type=int, default=5,
                        help="Default minimum star threshold (default: 5; Codeberg repos have fewer stars)")
    parser.add_argument("--per-page", type=int, default=20,
                        help="Results per page (max 50)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without writing files")
    parser.add_argument("--sleep", type=float, default=2.0,
                        help="Seconds between queries (default: 2)")
    parser.add_argument("--max-pages", type=int, default=5,
                        help="Max pages per query (default: 5)")
    parser.add_argument("--from", dest="from_idx", type=int, default=0,
                        help="Start at query index")
    parser.add_argument("--to", dest="to_idx", type=int, default=None,
                        help="Stop at query index (inclusive)")
    parser.add_argument("--host", type=str, default=CODEBERG_HOST,
                        help="Codeberg host URL (default: https://codeberg.org)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output file path (default: repos.yaml)")
    args = parser.parse_args()

    cfg = research_config.require_valid_config()
    queries = load_codeberg_queries(cfg)

    if not queries:
        topic_name = cfg.get("topic", {}).get("name", "your topic")
        print("ERROR: No codeberg_queries defined in config/taxonomy.yaml.", file=sys.stderr)
        print("Add a ``codeberg_queries`` section, e.g.:", file=sys.stderr)
        print("", file=sys.stderr)
        print("codeberg_queries:", file=sys.stderr)
        print(f'  - query: "{_norm(topic_name)}"', file=sys.stderr)
        print('    category: method', file=sys.stderr)
        print('  - query: "YOUR KEYWORD tool"', file=sys.stderr)
        print('    category: application', file=sys.stderr)
        print('    min_stars: 10', file=sys.stderr)
        print("", file=sys.stderr)
        print("See: https://codeberg.org/api/swagger", file=sys.stderr)
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
    print(f"Running {len(active)}/{len(queries)} queries on {args.host} "
          f"(min-stars {args.min_stars})...", flush=True)

    all_new = []
    total_results = 0
    filtered_out = 0

    for qi, qinfo in enumerate(active, start=args.from_idx):
        query_text = qinfo["query"]
        cat = qinfo.get("category", "")
        hint = qinfo.get("subcategory_hint", "")
        q_min_stars = qinfo.get("min_stars", args.min_stars)
        q_owner = qinfo.get("owner", "")

        label = f"[{cat}]" if cat else f"[q{qi}]"
        print(f"\nQuery {qi + 1}/{len(queries)} {label} {query_text[:80]}", flush=True)

        for page in range(1, args.max_pages + 1):
            items, total = codeberg_search_repos(
                query_text, args.host,
                per_page=args.per_page, page=page,
                owner=q_owner if q_owner else None,
            )
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

                # Client-side star filtering (API doesn't support min_stars)
                if (item.get("stargazers_count") or 0) < q_min_stars:
                    continue

                desc = item.get("description") or ""
                topics = item.get("topics", []) or []

                if not is_relevant_repo(name, desc, topics, signal_re):
                    filtered_out += 1
                    continue

                existing_names.add(name.lower().strip())
                raw = codeberg_to_raw(item)
                entry = normalize_entry(raw, cat, hint, cfg)
                all_new.append(entry)
                page_new += 1

            print(f"  page {page}: {len(items)} results, {page_new} new, "
                  f"{len(items) - page_new} dup/filtered", flush=True)

            if len(items) < args.per_page:
                break

        time.sleep(args.sleep)

    print(f"\n{'='*60}", flush=True)
    print(f"Total results scanned: {total_results}", flush=True)
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
    total_stars = sum(e["stars"] for e in all_new)

    print("\nCategory breakdown:", flush=True)
    for c, count in cats.most_common():
        print(f"  {c:20} {count:4}", flush=True)

    print(f"\nTotal new stars: {total_stars:,}", flush=True)


if __name__ == "__main__":
    main()
