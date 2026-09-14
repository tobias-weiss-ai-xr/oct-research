#!/usr/bin/env python3
"""Bulk-fetch metadata (authors, abstract, venue hint) from arXiv API.

Uses arXiv's id_list batch endpoint (~100 IDs per request) for speed.
Skips papers that already have authors populated.
"""
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
import yaml

ARXIV_ID_PATTERN = re.compile(r"(\d{4}\.\d{4,5})")
ARXIV_API = "https://export.arxiv.org/api/query"
BATCH_SIZE = 50  # arXiv allows up to ~300, but 50 is safe and fast
API_DELAY = 3    # arXiv asks for 3s between requests


def extract_arxiv_id(url):
    match = ARXIV_ID_PATTERN.search(url)
    return match.group(1) if match else None


def fetch_batch(arxiv_ids):
    """Fetch metadata for a batch of arXiv IDs. Returns dict {id: metadata}."""
    results = {}
    id_list = ",".join(arxiv_ids)
    for attempt in range(4):
        try:
            resp = requests.get(
                ARXIV_API,
                params={"id_list": id_list, "max_results": len(arxiv_ids)},
                timeout=60,
            )
            if resp.status_code == 429:
                wait = 30 * (attempt + 1)
                print(f"    429, waiting {wait}s (attempt {attempt+1}/4)...", flush=True)
                time.sleep(wait)
                continue
            if resp.status_code == 503:
                print(f"    503, waiting 60s...", flush=True)
                time.sleep(60)
                continue
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
            ns = {"atom": "http://www.w3.org/2005/Atom",
                  "arxiv": "http://arxiv.org/schemas/atom"}
            for entry in root.findall("atom:entry", ns):
                # Extract arXiv ID from the entry's id field
                id_elem = entry.find("atom:id", ns)
                if id_elem is None or not id_elem.text:
                    continue
                entry_url = id_elem.text.strip()
                m = ARXIV_ID_PATTERN.search(entry_url)
                if not m:
                    continue
                aid = m.group(1)

                authors = []
                for author in entry.findall("atom:author", ns):
                    name = author.find("atom:name", ns)
                    if name is not None and name.text:
                        authors.append(name.text.strip())

                summary = entry.find("atom:summary", ns)
                abstract = summary.text.strip() if summary is not None and summary.text else ""
                # Clean whitespace in abstract
                abstract = re.sub(r"\s+", " ", abstract) if abstract else ""

                published = entry.find("atom:published", ns)
                date = published.text[:7] if published is not None and published.text else ""

                # Try to extract venue hint from arxiv:comment
                comment_elem = entry.find("arxiv:comment", ns)
                venue = ""
                if comment_elem is not None and comment_elem.text:
                    comment = comment_elem.text.strip()
                    # Look for common venue patterns
                    venue_match = re.search(
                        r"(?:Accepted|Published|Appears in|in proceedings of|in|at)\s+"
                        r"((?:ACL|EMNLP|NAACL|NeurIPS|ICML|ICLR|CVPR|ICCV|ECCV|AAAI|"
                        r"IJCAI|COLM|COLING|KDD|WWW|SIGIR|WSDM|CIKM|TMLR|JMLR|ICRA|IROS|RA-L|"
                        r"CoRL|RSS|Humanoids|CASE|IROS|RAL)[\w\s\.\-]*"
                        r"(?:\d{4})?)",
                        comment, re.IGNORECASE
                    )
                    if venue_match:
                        venue = venue_match.group(1).strip()

                # Try DOI link for venue
                for link in entry.findall("atom:link", ns):
                    if link.get("title") == "doi":
                        doi = link.get("href", "").replace("http://dx.doi.org/", "")
                        if doi and not venue:
                            venue = doi
                        break

                # Extract code/project URLs from abstract or comment
                code_url = ""
                project_url = ""
                search_text = abstract + " " + (comment_elem.text if comment_elem is not None and comment_elem.text else "")
                github_match = re.search(r"https?://github\.com/[\w\-.]+/[\w\-.]+", search_text)
                if github_match:
                    code_url = github_match.group(0).rstrip(".")
                proj_match = re.search(r"https?://(?:[\w\-.]+\.)?(?:github\.io|sites\.google\.com|huggingface\.co|zenodo\.org|projectpage\.[\w\-.]+)/[^\s\)]+", search_text)
                if proj_match:
                    project_url = proj_match.group(0).rstrip(".")
                # If only a github.io match and no code_url, treat github.io as project_url
                if not code_url and not project_url:
                    gh_io_match = re.search(r"https?://[\w\-.]+\.github\.io/[^\s\)]+", search_text)
                    if gh_io_match:
                        project_url = gh_io_match.group(0).rstrip(".")

                results[aid] = {
                    "authors": authors,
                    "abstract": abstract,
                    "date": date,
                    "venue": venue,
                    "code_url": code_url,
                    "project_url": project_url,
                }
            time.sleep(API_DELAY)
            return results
        except requests.exceptions.Timeout:
            print(f"    Timeout, waiting 30s (attempt {attempt+1}/4)...", flush=True)
            time.sleep(30)
        except Exception as e:
            print(f"    ERR: {e} (attempt {attempt+1}/4)", flush=True)
            time.sleep(15)
    return results


def main():
    yaml_path = Path(__file__).resolve().parent.parent / "papers.yaml"
    if not yaml_path.exists():
        print(f"ERROR: {yaml_path} not found", flush=True)
        sys.exit(1)

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    papers = data.get("papers", [])
    total = len(papers)
    print(f"Loaded {total} papers from papers.yaml", flush=True)

    # Build index of papers needing enrichment: arxiv_id -> list of paper dicts
    # (a paper may appear multiple times across categories)
    needs_enrichment = {}  # arxiv_id -> [paper, paper, ...]
    for paper in papers:
        if paper.get("authors"):  # already has authors, skip
            continue
        aid = extract_arxiv_id(paper.get("url", ""))
        if not aid:
            continue
        needs_enrichment.setdefault(aid, []).append(paper)

    to_fetch = list(needs_enrichment.keys())
    print(f"Papers needing enrichment: {len(to_fetch)} unique arXiv IDs", flush=True)
    print(f"(covering {sum(len(v) for v in needs_enrichment.values())} YAML entries)", flush=True)

    if not to_fetch:
        print("Nothing to do — all papers already have authors.", flush=True)
        return

    # Fetch in batches
    batches = [to_fetch[i:i + BATCH_SIZE] for i in range(0, len(to_fetch), BATCH_SIZE)]
    print(f"Will fetch in {len(batches)} batches of up to {BATCH_SIZE} IDs", flush=True)
    print("=" * 70, flush=True)

    fetched = 0
    updated_entries = 0
    skipped = 0

    for bi, batch in enumerate(batches):
        print(f"Batch {bi+1}/{len(batches)}: fetching {len(batch)} IDs...", flush=True)
        results = fetch_batch(batch)
        for aid in batch:
            if aid not in results:
                skipped += 1
                continue
            meta = results[aid]
            fetched += 1
            for paper in needs_enrichment[aid]:
                changed = False
                if meta["authors"] and not paper.get("authors"):
                    paper["authors"] = meta["authors"]
                    changed = True
                if meta["abstract"] and not paper.get("abstract"):
                    paper["abstract"] = meta["abstract"]
                    changed = True
                if meta["date"] and not paper.get("date"):
                    paper["date"] = meta["date"]
                    changed = True
                if meta["venue"] and not paper.get("venue"):
                    paper["venue"] = meta["venue"]
                    changed = True
                if meta.get("code_url") and not paper.get("code_url"):
                    paper["code_url"] = meta["code_url"]
                    changed = True
                if meta.get("project_url") and not paper.get("project_url"):
                    paper["project_url"] = meta["project_url"]
                    changed = True
                if changed:
                    updated_entries += 1

    print("=" * 70, flush=True)
    print(f"Fetched metadata for {fetched}/{len(to_fetch)} arXiv IDs", flush=True)
    print(f"Skipped (not found): {skipped}", flush=True)
    print(f"Updated {updated_entries} YAML entries", flush=True)

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    print(f"Saved to {yaml_path}", flush=True)


if __name__ == "__main__":
    main()
