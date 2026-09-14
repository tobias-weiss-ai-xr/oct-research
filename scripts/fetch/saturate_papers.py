#!/usr/bin/env python3
"""Saturate papers.yaml by searching arXiv comprehensively.

Builds diverse queries by expanding the base arxiv_queries from
config/taxonomy.yaml across cs.AI, cs.CL, cs.LG, cs.RO within a 48-month
window. Auto-classifies, deduplicates, and loops until saturation (<5 new).
Saves after each round to survive timeouts.
"""

import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
import yaml

import research_config

ARXIV_ID_PATTERN = re.compile(r"(\d{4}\.\d{4,5})")
ARXIV_SEARCH_API = (
    "https://export.arxiv.org/api/query?search_query={}&start={}&max_results={}"
)
API_DELAY = 3
SATURATION_THRESHOLD = 5
MAX_RESULTS_PER_QUERY = 100
MONTHS_BACK = 48
MAX_ROUNDS = 3

def get_queries(cfg):
    """Expand arxiv_queries across multiple arXiv categories.

    If a query already specifies a cat: clause, it is used as-is.
    Otherwise, the query is expanded across the categories defined in
    config/taxonomy.yaml (arxiv_expand_cats) or a default set.
    Supports both string and dict query formats (like fetch_new_papers.py).
    """
    base = cfg.get("arxiv_queries", [])
    # Config can specify which arXiv categories to expand across
    expand_cats = cfg.get("arxiv_expand_cats", ["cs.AI", "cs.LG", "cs.RO"])
    out = []
    for q in base:
        if isinstance(q, dict):
            query_str = q.get("query", "")
            q_category = q.get("category", "")
            q_hint = q.get("subcategory_hint", "")
        else:
            query_str = q
            q_category = ""
            q_hint = ""
        m = re.match(r'cat:([\w.]+)\s+AND\s+(.+)', query_str)
        if m:
            clause = m.group(2)
            # Keep original category, also expand across other cats
            out.append({"query": query_str, "category": q_category, "subcategory_hint": q_hint})
            for c in expand_cats:
                if c != m.group(1):
                    out.append({"query": f'cat:{c} AND {clause}', "category": q_category, "subcategory_hint": q_hint})
        else:
            # No cat: prefix — expand across all expand_cats
            for c in expand_cats:
                out.append({"query": f'cat:{c} AND {query_str}', "category": q_category, "subcategory_hint": q_hint})
    return out or [{"query": f'cat:cs.AI AND abs:"{cfg.get("topic", {}).get("short", "research")}"', "category": "", "subcategory_hint": ""}]


def load_existing_papers(yaml_path):
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    papers = data.get("papers", [])
    by_id = {}
    titles_lower = []
    for p in papers:
        url = p.get("url", "")
        match = ARXIV_ID_PATTERN.search(url)
        if match:
            by_id[match.group(1)] = p
        titles_lower.append(p.get("title", "").lower().strip())
    return data, papers, by_id, titles_lower


def title_similarity(a, b):
    a_clean = re.sub(r"[^\w\s]", "", a.lower())
    b_clean = re.sub(r"[^\w\s]", "", b.lower())
    return SequenceMatcher(None, a_clean, b_clean).ratio()


def search_arxiv(query, months_back):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(days=months_back * 30)
    date_start = cutoff.strftime("%Y%m%d0000")
    date_end = now.strftime("%Y%m%d") + "2359"

    full_query = f"({query}) AND submittedDate:[{date_start} TO {date_end}]"
    try:
        resp = requests.get(
            ARXIV_SEARCH_API.format(
                requests.utils.quote(full_query), 0, MAX_RESULTS_PER_QUERY
            ),
            timeout=30,
        )
        resp.raise_for_status()
        entries = []
        root = resp.text
        for match in re.finditer(r"<entry>(.*?)</entry>", root, re.DOTALL):
            entry_xml = match.group(1)
            entry = {}
            title_m = re.search(r"<title>(.*?)</title>", entry_xml, re.DOTALL)
            if title_m:
                entry["title"] = re.sub(r"\s+", " ", title_m.group(1).strip())
            id_m = re.search(r"<id>(.*?)</id>", entry_xml)
            if id_m:
                entry["url"] = id_m.group(1).strip().replace("http://", "https://")
            published_m = re.search(r"<published>(.*?)</published>", entry_xml)
            if published_m:
                entry["date"] = published_m.group(1).strip()[:7]
            summary_m = re.search(r"<summary>(.*?)</summary>", entry_xml, re.DOTALL)
            if summary_m:
                entry["abstract"] = re.sub(r"\s+", " ", summary_m.group(1).strip())
            if entry.get("title") and entry.get("url"):
                entries.append(entry)
        return entries
    except Exception as e:
        print(f"  WARNING: arXiv search error: {e}", flush=True)
        return []


def load_relevance_keywords(cfg):
    """Load relevance keywords from config/taxonomy.yaml.

    Returns a list of keyword strings. A paper is considered relevant if
    any keyword appears in its title or abstract.
    Falls back to the topic short name if no keywords are configured.
    """
    kws = cfg.get("relevance_keywords", [])
    if kws:
        return kws
    # Fallback: use topic short name and category names
    short = cfg.get("topic", {}).get("short", "")
    cats = [c.get("id", "") for c in cfg.get("taxonomy", {}).get("categories", [])]
    return [short] + cats if short else cats


def is_relevant(title, abstract, relevance_keywords=None):
    """Check if a paper is relevant based on config-driven keywords."""
    if not relevance_keywords:
        return True  # No filter — accept all
    text = f"{title} {abstract}".lower()
    return any(kw.lower() in text for kw in relevance_keywords)


def dedup_title(title, titles_lower, threshold=0.75):
    title_clean = title.lower().strip()
    for existing in titles_lower:
        if title_similarity(title_clean, existing) >= threshold:
            return True
    return False


def save_papers(yaml_path, data, papers):
    data["papers"] = papers
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(
            data,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )


def run_round(yaml_path, data, papers, by_id, titles_lower, queries, round_num, cfg, relevance_keywords):
    print(f"\n{'=' * 60}", flush=True)
    print(f"ROUND {round_num}", flush=True)
    print(f"{'=' * 60}", flush=True)

    round_new = []
    seen_ids = set()
    seen_titles = set(titles_lower)

    # Import classify_subcategory from fetch_new_papers for config-driven classification
    from fetch_new_papers import classify_subcategory

    for qi, qinfo in enumerate(queries):
        query = qinfo["query"]
        q_category = qinfo.get("category", "")
        q_hint = qinfo.get("subcategory_hint", "")
        cat_match = re.search(r"cat:(\S+)", query)
        cat = cat_match.group(1) if cat_match else "?"
        print(
            f"\n  Query {qi + 1}/{len(queries)} [{cat}]...",
            flush=True,
        )

        entries = search_arxiv(query, MONTHS_BACK)
        print(f"    arXiv returned {len(entries)} entries", flush=True)

        for entry in entries:
            arxiv_id_match = ARXIV_ID_PATTERN.search(entry.get("url", ""))
            arxiv_id = arxiv_id_match.group(1) if arxiv_id_match else None

            if arxiv_id and arxiv_id in by_id:
                continue

            if arxiv_id and arxiv_id in seen_ids:
                continue

            title = entry.get("title", "")
            title_lower = title.lower().strip()

            if title_lower in seen_titles:
                continue

            if dedup_title(title, titles_lower):
                continue

            abstract = entry.get("abstract", "")

            if not is_relevant(title, abstract, relevance_keywords):
                continue

            # Config-driven classification
            cat = q_category or ""
            sub = q_hint or classify_subcategory(title, abstract, cfg)

            new_paper = {
                "title": title,
                "date": entry.get("date", ""),
                "url": entry.get("url", ""),
                "category": cat,
                "subcategory": sub,
                "authors": [],
                "venue": "",
                "code_url": "",
                "project_url": "",
                "abstract": abstract,
                "tags": [f"auto-{cat}", f"auto-{sub}"] if cat else [f"auto-{sub}"],
            }

            if arxiv_id:
                seen_ids.add(arxiv_id)
            seen_titles.add(title_lower)
            titles_lower.append(title_lower)
            round_new.append(new_paper)
            by_id[arxiv_id] = new_paper

            print(
                f"    NEW [{cat}/{sub}] {title[:70]}",
                flush=True,
            )

        time.sleep(API_DELAY)

        if (qi + 1) % 20 == 0:
            save_papers(yaml_path, data, papers + round_new)
            print(
                f"    [checkpoint] saved {len(papers) + len(round_new)} papers",
                flush=True,
            )

    print(f"\n  Round {round_num} found {len(round_new)} new papers", flush=True)
    return round_new


def main():
    cfg = research_config.require_valid_config()
    queries = get_queries(cfg)
    relevance_keywords = load_relevance_keywords(cfg)

    yaml_path = Path(__file__).resolve().parent.parent.parent / "papers.yaml"
    data, papers, by_id, titles_lower = load_existing_papers(yaml_path)

    print(f"Loaded {len(papers)} existing papers", flush=True)
    print(f"Using {len(queries)} queries (expanded from config/taxonomy.yaml)", flush=True)
    print(f"Relevance keywords: {len(relevance_keywords)} configured", flush=True)
    print(f"Search window: {MONTHS_BACK} months", flush=True)

    total_new = 0
    round_num = 1

    while round_num <= MAX_ROUNDS:
        round_new = run_round(
            yaml_path, data, papers, by_id, titles_lower, queries, round_num, cfg, relevance_keywords
        )

        papers.extend(round_new)
        total_new += len(round_new)

        save_papers(yaml_path, data, papers)
        print(f"  Saved {len(papers)} total papers to {yaml_path}", flush=True)

        if len(round_new) < SATURATION_THRESHOLD:
            print(
                f"\nSATURATED: Round {round_num} found only {len(round_new)} "
                f"new papers (< {SATURATION_THRESHOLD} threshold)",
                flush=True,
            )
            break

        print(
            f"\n  Total new so far: {total_new}, starting round {round_num + 1}...",
            flush=True,
        )
        round_num += 1

    if round_num > MAX_ROUNDS:
        print(
            f"\nReached max rounds ({MAX_ROUNDS}). Stopping.",
            flush=True,
        )

    if total_new == 0:
        print("\nNo new papers found. papers.yaml unchanged.", flush=True)

    # Config-driven distribution summary
    cats = research_config.get_categories(cfg)
    subs = research_config.get_subcategories(cfg)

    cat_counter = Counter()
    sub_counter = Counter()
    for p in papers:
        cat_counter[p.get("category", "unknown")] += 1
        sub_counter[p.get("subcategory", "unknown")] += 1

    print(f"\n{'=' * 60}", flush=True)
    print("FINAL DISTRIBUTION", flush=True)
    print(f"{'=' * 60}", flush=True)
    print(f"Total papers: {len(papers)}", flush=True)
    print(f"New papers added: {total_new}", flush=True)
    print(f"Rounds: {round_num}", flush=True)
    print(f"\nBy category:", flush=True)
    for cat in cats:
        cid = cat["id"]
        print(f"  {cid}: {cat_counter.get(cid, 0)}", flush=True)
    print(f"\nBy subcategory:", flush=True)
    for sub in subs:
        sid = sub["id"]
        print(f"  {sid}: {sub_counter.get(sid, 0)}", flush=True)


if __name__ == "__main__":
    main()
