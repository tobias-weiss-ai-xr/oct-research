#!/usr/bin/env python3
"""Auto-detect code URLs for papers missing code_url field.

Queries Semantic Scholar and Papers with Code APIs to find GitHub repositories
associated with each paper's arXiv ID.
"""

import argparse
import re
import sys
import time
from pathlib import Path

import requests
import yaml

ARXIV_ID_PATTERN = re.compile(r"(\d{4}\.\d{4,5})")
SS_BASE = "https://api.semanticscholar.org/graph/v1/paper/arXiv:{}"
SS_FIELDS = "externalIds,is_open_access,openAccessPdf"
PWC_BASE = "https://paperswithcode.com/api/v1/papers/"
API_DELAY = 1


def extract_arxiv_id(url):
    match = ARXIV_ID_PATTERN.search(url)
    return match.group(1) if match else None


def fetch_semantic_scholar(arxiv_id):
    try:
        resp = requests.get(
            SS_BASE.format(arxiv_id),
            params={"fields": SS_FIELDS},
            timeout=30,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  WARNING: Semantic Scholar error for {arxiv_id}: {e}", flush=True)
        return None


def fetch_papers_with_code(arxiv_id):
    try:
        resp = requests.get(f"{PWC_BASE}{arxiv_id}/", timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        repo_url = (data.get("repo_url") or "").strip()
        if repo_url:
            return repo_url
        # Check if there's a code URL in the links
        for link in data.get("links", []):
            url = link.get("url", "")
            if "github.com" in url or "gitlab" in url or "huggingface" in url:
                return url
        return None
    except Exception as e:
        print(f"  WARNING: PwC error for {arxiv_id}: {e}", flush=True)
        return None


def find_code_url(arxiv_id):
    url = None

    # Strategy 1: Semantic Scholar — check externalIds
    ss_data = fetch_semantic_scholar(arxiv_id)
    if ss_data:
        ext_ids = ss_data.get("externalIds") or {}
        for key in ("CorpusId", "DOI", "PubMed"):
            pass  # these don't give GitHub URLs directly
        # Check openAccessPdf as a fallback
        if not url:
            oa_pdf = (ss_data.get("openAccessPdf") or {}).get("url", "")
            if oa_pdf and "github.com" in oa_pdf:
                url = oa_pdf

    # Strategy 2: Papers with Code
    time.sleep(API_DELAY)
    pwc_url = fetch_papers_with_code(arxiv_id)
    if pwc_url:
        url = pwc_url

    return url or None


def main():
    parser = argparse.ArgumentParser(description="Auto-detect code URLs for papers")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without modifying papers.yaml"
    )
    parser.add_argument("--limit", type=int, help="Max papers to check (for testing)")
    args = parser.parse_args()

    yaml_path = Path(__file__).resolve().parent.parent / "papers.yaml"
    if not yaml_path.exists():
        print(f"ERROR: {yaml_path} not found", flush=True)
        sys.exit(1)

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    papers = data.get("papers", [])
    total = len(papers)

    # Find papers missing code_url
    to_check = []
    for i, paper in enumerate(papers):
        existing = paper.get("code_url", "").strip()
        if existing:
            continue
        aid = extract_arxiv_id(paper.get("url", ""))
        if not aid:
            continue
        to_check.append((i, paper, aid))

    print(f"Loaded {total} papers, {len(to_check)} missing code_url", flush=True)

    if args.limit:
        to_check = to_check[: args.limit]

    if not to_check:
        print("Nothing to do — all papers have code_url.", flush=True)
        return

    found = 0
    for idx, (i, paper, aid) in enumerate(to_check):
        title = paper.get("title", "Untitled")[:60]
        print(f"[{idx + 1}/{len(to_check)}] Checking {aid}: {title}...", flush=True)

        code_url = find_code_url(aid)
        if code_url:
            print(f"  FOUND: {code_url}", flush=True)
            found += 1
            if not args.dry_run:
                paper["code_url"] = code_url

    if not args.dry_run and found > 0:
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(
                data, f, default_flow_style=False, allow_unicode=True, sort_keys=False
            )
        print(f"\nUpdated {found} papers with code URLs in {yaml_path}", flush=True)
    else:
        print(
            f"\nFound {found} code URLs (dry run, no files modified)"
            if args.dry_run
            else f"\nNo new code URLs found",
            flush=True,
        )


if __name__ == "__main__":
    main()
