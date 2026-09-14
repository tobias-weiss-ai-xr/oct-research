#!/usr/bin/env python3
"""Discover GitLab projects relevant to your research topic.

Reads queries from ``config/taxonomy.yaml`` under the ``gitlab_queries`` key.
Uses the **GitLab public REST API** (no ``glab`` CLI required).

GitLab search docs:
  https://docs.gitlab.com/ee/api/projects.html#list-projects

Note: GitLab's /projects endpoint does not support ``order_by=stars`` for
search queries.  Results are sorted by last activity and star filtering
is applied client-side.

Requirements:
  - Internet access (GitLab API is public, no token needed for search)
  - ``pip install pyyaml requests``

Usage:
    python3 scripts/fetch/fetch_gitlab_repos.py --dry-run
    python3 scripts/fetch/fetch_gitlab_repos.py --min-stars 5
    python3 scripts/fetch/fetch_gitlab_repos.py --host https://gitlab.gwdg.de

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
)

GITLAB_API = os.environ.get("GITLAB_HOST", "https://gitlab.com") + "/api/v4"
USER_AGENT = "Research-Corpus/1.0 (mailto:business@tobias-weiss.org)"


# ── Config loading ────────────────────────────────────────────────────────

def load_gitlab_queries(cfg):
    """Load gitlab_queries from taxonomy.yaml.

    Each entry must have ``query``.  Optional: ``category``,
    ``subcategory_hint``, ``min_stars``, ``topics`` (list of GitLab topic
    filters, e.g. ``["devops", "ci-cd"]``).

    GitLab search syntax:
      - Plain text search by project name/description
      - No boolean operators — the API does substring matching
      - ``topics`` filter is a separate parameter (all topics must match)
    """
    queries = []
    for item in cfg.get("gitlab_queries", []):
        q = item.get("query", "")
        if not q:
            continue
        queries.append({
            "query": q,
            "category": item.get("category", ""),
            "subcategory_hint": item.get("subcategory_hint", ""),
            "min_stars": item.get("min_stars"),
            "topics": item.get("topics", []),
            "language": item.get("language", ""),  # optional language filter
        })
    return queries


# ── GitLab API helpers ───────────────────────────────────────────────────

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


def gitlab_search_projects(query, host, min_stars=5, topics=None,
                           language=None, per_page=20, page=1):
    """Search GitLab projects via REST API.  Returns (items, total_count).

    GitLab uses ``star_count`` (not ``stargazers_count``).  Pagination uses
    ``page`` + ``per_page`` (max 100 per page).
    """
    params = {
        "search": query,
        "order_by": "last_activity_at",  # GitLab rejects stars; sort client-side
        "sort": "desc",
        "per_page": per_page,
        "page": page,
        "simple": "true",          # exclude forks by default
        "membership": "false",     # search all public projects
    }
    if topics:
        params["topic"] = ",".join(topics)
    if language:
        params["programming_language"] = language

    resp = http_get_with_retry(
        session, f"{host}/api/v4/projects", params=params,
        timeout=30, rate_limit_wait=60,
    )
    if resp is None:
        return [], 0

    if resp.status_code >= 400:
        print(f"  WARNING: GitLab API {resp.status_code}: {resp.text[:100]}", flush=True)
        return [], 0

    try:
        data = resp.json()
    except ValueError:
        return [], 0
    if not isinstance(data, list):
        return [], 0

    # Filter by star count client-side (API has no min_stars param)
    items = [p for p in data if (p.get("star_count") or 0) >= min_stars]
    total = int(resp.headers.get("X-Total", len(items)))
    return items, total


def gitlab_to_raw(item):
    """Map a GitLab project to a normalised raw dict."""
    license_info = item.get("license", {}) or {}
    license_name = ""
    if isinstance(license_info, dict):
        license_name = license_info.get("spdx_id", license_info.get("name", ""))
    elif isinstance(license_info, str):
        license_name = license_info

    topics = item.get("topics", []) or []
    # GitLab doesn't return primary language in project search results
    lang = ""
    topics_raw = item.get("topics", []) or []
    if isinstance(topics_raw, str):
        topics = [t.strip() for t in topics_raw.split(",") if t.strip()]
    else:
        topics = topics_raw

    return {
        "name": item.get("path_with_namespace", item.get("path", "")),
        "url": item.get("web_url", item.get("http_url_to_repo", "")),
        "description": item.get("description") or "",
        "stars": item.get("star_count", 0),
        "forks": item.get("forks_count", 0),
        "language": lang,
        "topics": topics,
        "pushed_at": (item.get("last_activity_at", "") or "")[:10],
        "created_at": (item.get("created_at", "") or "")[:10],
        "open_issues": item.get("open_issues_count", 0),
        "license": license_name,
    }


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Discover GitLab projects relevant to your research topic."
    )
    parser.add_argument("--min-stars", type=int, default=5,
                        help="Default minimum star threshold (default: 5; GitLab repos typically have fewer stars)")
    parser.add_argument("--per-page", type=int, default=20,
                        help="Results per page (max 100)")
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
    parser.add_argument("--host", type=str,
                        default=os.environ.get("GITLAB_HOST", "https://gitlab.com"),
                        help="GitLab host URL (default: https://gitlab.com)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output file path (default: repos.yaml)")
    args = parser.parse_args()

    cfg = research_config.require_valid_config()
    queries = load_gitlab_queries(cfg)

    if not queries:
        topic_name = cfg.get("topic", {}).get("name", "your topic")
        print("ERROR: No gitlab_queries defined in config/taxonomy.yaml.", file=sys.stderr)
        print("Add a ``gitlab_queries`` section, e.g.:", file=sys.stderr)
        print("", file=sys.stderr)
        print("gitlab_queries:", file=sys.stderr)
        print(f'  - query: "{_norm(topic_name)}"', file=sys.stderr)
        print('    category: method', file=sys.stderr)
        print('  - query: "YOUR KEYWORD tool"', file=sys.stderr)
        print('    category: application', file=sys.stderr)
        print('    min_stars: 10', file=sys.stderr)
        print('    topics:', file=sys.stderr)
        print('      - "devops"', file=sys.stderr)
        print("", file=sys.stderr)
        print("See: https://docs.gitlab.com/ee/api/projects.html#search-for-projects-by-name",
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
        q_topics = qinfo.get("topics", [])
        q_lang = qinfo.get("language", "")

        label = f"[{cat}]" if cat else f"[q{qi}]"
        print(f"\nQuery {qi + 1}/{len(queries)} {label} {query_text[:80]}", flush=True)

        for page in range(1, args.max_pages + 1):
            items, total = gitlab_search_projects(
                query_text, args.host, min_stars=q_min_stars,
                topics=q_topics if q_topics else None,
                language=q_lang if q_lang else None,
                per_page=args.per_page, page=page,
            )
            if qi == args.from_idx and page == 1:
                total_results += total
                print(f"  {total} total results", flush=True)

            if not items:
                break

            page_new = 0
            for item in items:
                name = item.get("path_with_namespace", item.get("path", ""))
                if name.lower().strip() in existing_names:
                    continue

                desc = item.get("description") or ""
                topics = item.get("topics", []) or []

                if not is_relevant_repo(name, desc, topics, signal_re):
                    filtered_out += 1
                    continue

                existing_names.add(name.lower().strip())
                raw = gitlab_to_raw(item)
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
