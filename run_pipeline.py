"""Skeleton research: automated news / intelligence ingestion pipeline.

Ingests RSS/Atom feeds, arXiv queries, GitHub release feeds and structured
catalogs (e.g. CISA KEV), classifies + scores them, de-duplicates against a
seen-history, and renders a daily digest (Markdown + HTML + JSON).

Run:
    python run_pipeline.py            # full ingest -> digest (writes + marks seen)
    python run_pipeline.py --dry-run  # ingest + score only (no writes, no seen)
    python run_pipeline.py --top 30   # smaller digest
    python run_pipeline.py --json-out data/raw.json

Sources, weights and keywords are configured in ``config/sources.yml``.

Anti-saturation controls (see config/sources.yml):
  * ``recent_days`` / ``default_recent_days`` — drop items older than N days.
    Applied to RSS + catalog sources by default so static catalogs (CISA KEV)
    and full-archive feeds (Snyk) stop recycling old items every run.
  * ``max_source_share`` — cap how many of the digest slots a single source
    may occupy, so one high-volume feed cannot crowd out everything else.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
from datetime import datetime as _dt
from datetime import timedelta
from datetime import timezone
from pathlib import Path

import yaml

from ingest import digest, fetch
from ingest.classify import Classifier
from ingest.dedup import DedupStore

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CONFIG_PATH = ROOT / "config" / "sources.yml"
STATE_PATH = DATA / "seen.json"


def _parse_date(pub: str):
    """Parse an ISO-8601 (or epoch) timestamp to a tz-aware datetime, or None."""
    if not pub:
        return None
    try:
        dt = _dt.fromisoformat(pub.replace("Z", "+00:00"))
    except ValueError:
        try:
            return _dt.fromtimestamp(float(pub), tz=timezone.utc)
        except (ValueError, TypeError, OverflowError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _within_recent(published: str, cutoff) -> bool:
    """True if the item should be kept.

    Items without a parseable published date are ALWAYS kept — we never
    silently drop content we cannot date.
    """
    if cutoff is None:
        return True
    dt = _parse_date(published)
    if dt is None:
        return True
    return dt >= cutoff


def select_with_quota(items: list[dict], top_n: int, max_share: float) -> list[dict]:
    """Select the top-scoring ``top_n`` items with a HARD per-source ceiling.

    A round-robin greedy picks, on each pass, the highest-scoring item from a
    source still below its quota.  This guarantees no single source can occupy
    more than ``quota = max(1, int(top_n * max_share))`` digest slots, so one
    high-volume feed cannot crowd out the rest.  Any unfilled slots (e.g. when
    there are fewer sources than ``quota``) are topped up with the next-highest
    items regardless of source.
    """
    if top_n <= 0 or not items:
        return []
    quota = max(1, int(top_n * max_share))
    chosen: list[dict] = []
    chosen_digests: set[str] = set()
    used: dict[str, int] = {}

    remaining = list(items)  # pre-sorted by score descending
    while len(chosen) < top_n:
        picked = False
        for it in remaining:
            if len(chosen) >= top_n:
                break
            if it["digest"] in chosen_digests:
                continue
            src = it.get("source", "")
            if used.get(src, 0) < quota:
                chosen.append(it)
                chosen_digests.add(it["digest"])
                used[src] = used.get(src, 0) + 1
                picked = True
                break
        if not picked:
            break

    if len(chosen) < top_n:
        for it in remaining:
            if len(chosen) >= top_n:
                break
            if it["digest"] not in chosen_digests:
                chosen.append(it)
                chosen_digests.add(it["digest"])

    return chosen


def main():
    ap = argparse.ArgumentParser(description="News / intelligence ingestion pipeline")
    ap.add_argument("--config", default=str(CONFIG_PATH))
    ap.add_argument("--state", default=str(STATE_PATH))
    ap.add_argument("--dry-run", action="store_true",
                    help="don't write files or mark items seen")
    ap.add_argument("--json-out", default=str(DATA / "raw.json"))
    ap.add_argument("--top", type=int, default=60, help="max digest items")
    args = ap.parse_args()

    conf = yaml.safe_load(Path(args.config).read_text())
    outdir = Path(args.json_out).parent

    default_recent = conf.get("default_recent_days", 0)
    max_share = conf.get("max_source_share", 0.4)

    clf = Classifier(conf.get("keywords", {}),
                     fresh_window_days=conf.get("fresh_window_days", 3))
    f = fetch.Fetcher(timeout=25)
    store = DedupStore(args.state, retention_days=conf.get("retention_days", 14))

    print(f"[pipeline] ingesting from {len(conf['sources'])} sources")
    fresh: list[dict] = []

    for src in conf["sources"]:
        name = src["name"]
        if delay := src.get("delay", 0):
            print(f"  (waiting {delay}s for {name})")
            time.sleep(delay)
        category = src.get("category", "discussion")
        weight = float(src.get("weight", 1.0))
        try:
            if src["type"] == "rss":
                raw = f.fetch_rss(src["url"], source=name, category=category,
                                  weight=weight)
            elif src["type"] == "arxiv":
                raw = f.fetch_arxiv(src["categories"], source=name,
                                    max_r=src.get("max", 40), weight=weight,
                                    query=src.get("query"))
            elif src["type"] == "github":
                raw = f.fetch_github_releases(src["repos"], source=name, weight=weight)
            elif src["type"] == "cisa_kev":
                raw = f.fetch_cisa_kev(src["url"], source=name,
                                       category=category, weight=weight)
            else:
                print(f"  [warn] unknown type for {name}: {src['type']}")
                continue
        except Exception as exc:  # noqa: BLE001
            print(f"  [error] {name}: {exc}")
            continue

        print(f"  {name}: {len(raw)} items")

        # Per-source hard cap (already-present in the format).
        max_items = src.get("max_items", 0)
        if max_items and len(raw) > max_items:
            raw = raw[:max_items]
            print(f"    (capped to {max_items})")

        # Anti-saturation: drop items older than recent_days.  RSS + catalog
        # sources default to default_recent_days; arxiv/github default to 0
        # (paper relevance / release notes are not recency-bound) unless an
        # explicit recent_days is set on the source.
        if src["type"] in ("rss", "cisa_kev"):
            recent_days = src.get("recent_days", default_recent)
        else:
            recent_days = src.get("recent_days", 0)
        if recent_days:
            cutoff = _dt.now(timezone.utc) - timedelta(days=recent_days)
            before = len(raw)
            raw = [it for it in raw if _within_recent(it.get("published"), cutoff)]
            if len(raw) != before:
                print(f"    (date-filtered to {len(raw)} within {recent_days}d)")

        for it in raw:
            tags = clf.tags(it)
            score = clf.score(it, source_weight=weight)
            it["tags"] = tags
            it["score"] = score
            min_topics = src.get("min_topics", 0)
            if min_topics and len(tags) < min_topics:
                continue
            if score >= conf.get("min_score", 0.4) and not store.seen(it["digest"]):
                fresh.append(it)

    fresh.sort(key=lambda x: x["score"], reverse=True)
    top = select_with_quota(fresh, args.top, max_share)

    print(f"[2] fresh items: {len(fresh)}; digest (quota {max_share:.0%}): "
          f"{len(top)}")

    if not args.dry_run:
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "raw.json").write_text(
            json.dumps(digest.render_json(top), indent=2, ensure_ascii=False),
            encoding="utf-8")
        gen = _dt.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        md = digest.render_markdown(top, gen)
        DATA.mkdir(parents=True, exist_ok=True)
        (DATA / "latest.md").write_text(md, encoding="utf-8")
        (DATA / "latest.html").write_text(digest.render_html(top, gen), encoding="utf-8")
        for it in top:
            store.mark_seen(it["digest"], it["title"], it["url"])
        store.save()
        print(f"[3] wrote data/latest.md, data/latest.html, {args.json_out}")
    else:
        print("[dry-run] no files written, nothing marked seen")

    print(f"[done] {store.stats()}")


if __name__ == "__main__":
    main()
