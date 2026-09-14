#!/usr/bin/env python3
"""Standard statistics generator for a *-research corpus.

Writes the standard structured outputs every research repo exposes:
  - statistics.json (metadata, by_category, by_subcategory, by_year, by_cell,
    momentum, category_trajectory, keyword_bursts, source_breakdown, venues,
    gaps, top_authors, emerging_themes_12m)
  - papers.json (paper metadata, newest first)
  - assets/graph_analysis.json (D3-style visualization data)

Self-contained: derives the taxonomy dynamically from papers.yaml.

Standard pipeline mimic shared across all research repos.

Usage:
    python3 scripts/standard_stats.py
    python3 scripts/standard_stats.py --check   # CI: fail if outputs stale
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import yaml

import readme_sections
import research_config

REPO = Path(__file__).resolve().parent.parent

BURST_KEYWORDS = [
    "reinforcement", "deep rl", "policy", "reward", "multi-agent", "agent",
    "agentic", "opponent", "hierarchical", "planning", "simulation",
    "world model", "decision", "optimization", "uncertainty", "bayesian",
    "transfer", "imitation", "offline", "memory", "retrieval", "learning",
    "self-supervised", "benchmark", "dataset", "survey", "human", "teaming",
    "autonomous", "scalable", "federated", "explainab", "diffusion",
    "language model", "multimodal", "graph", "skill", "tool", "embodied",
    "causal", "attention",
]
# Config-driven keywords override BURST_KEYWORDS when taxonomy.yaml defines them.
_CFG = research_config.require_valid_config()
BURST_KEYWORDS = research_config.get_trend_keywords(_CFG) or BURST_KEYWORDS


def _twelve_months_ago(now):
    y, m = now.year, now.month - 12
    while m <= 0:
        y -= 1
        m += 12
    return (y, m)


def _date_in(datestring, lo, end):
    if not datestring:
        return False
    try:
        y, m = int(datestring[:4]), int(datestring[5:7])
        return (y, m) >= lo and (y, m) < end
    except (ValueError, AttributeError):
        return False


def compute_all(entries):
    """Compute stats + papers.json + viz payload from paper entries.

    Returns (stats, papers_export, viz).  Pure computation — no I/O — so it
    can be reused for both writing and freshness ``--check``.
    """
    print(f"Parsed {len(entries)} papers")

    cats = [c for c in sorted({e.get("category", "unknown") for e in entries})
            if c != "unknown"] or ["unknown"]
    subs = sorted({e.get("subcategory", "unknown") for e in entries}) or ["unknown"]

    cat_counter = Counter(e.get("category", "unknown") for e in entries)
    sub_counter = Counter(e.get("subcategory", "unknown") for e in entries)
    cell_counter = Counter(f"{e.get('category','unknown')}/{e.get('subcategory','unknown')}" for e in entries)
    year_counter = Counter(e.get("date", "")[:4] for e in entries if e.get("date"))

    total = len(entries)
    total_cells = len(cats) * len(subs)
    filled_cells = len(cell_counter)
    saturation = round(filled_cells / total_cells * 100, 1) if total_cells else 0.0

    now = datetime.now()
    cur_lo = _twelve_months_ago(now)
    py, pm = cur_lo[0], cur_lo[1] - 12
    while pm <= 0:
        py -= 1
        pm += 12
    prev_lo = (py, pm)

    def is_recent(p):
        return _date_in(p.get("date", ""), cur_lo, (9999, 1))

    def is_prior(p):
        return _date_in(p.get("date", ""), prev_lo, cur_lo)

    cat_traj = {c: Counter() for c in cats}
    cat_recent, cat_total = Counter(), Counter()
    for e in entries:
        c = e.get("category", "unknown")
        if c not in cat_traj:
            continue
        y = e.get("date", "")[:4] if e.get("date") else "unknown"
        cat_traj[c][y] += 1
        cat_total[c] += 1
        if is_recent(e):
            cat_recent[c] += 1

    momentum = []
    for c in cats:
        t, r = cat_total[c], cat_recent[c]
        prior = sum(1 for e in entries if e.get("category") == c and is_prior(e))
        growth = round((r - prior) / prior * 100, 1) if prior > 0 else None
        recent_share = round(r / t, 3) if t else 0
        momentum.append({
            "id": c, "name": c.replace("-", " ").title(), "total": t,
            "recent": r, "prior": prior, "growth_pct": growth,
            "recent_share": recent_share,
            "papers_per_month": round(r / 12.0, 1),
            "score": round(recent_share * 100 + (growth or 0), 1),
        })
    momentum.sort(key=lambda m: -m["score"])

    trajectory = {
        c: {y: cat_traj[c][y] for y in sorted(y for y in cat_traj[c] if y != "unknown")}
        for c in cats
    }

    def text(p):
        return f"{p.get('title','')} {p.get('abstract','')}".lower()

    kw_t, kw_r = Counter(), Counter()
    for e in entries:
        t = text(e)
        for kw in BURST_KEYWORDS:
            if kw in t:
                kw_t[kw] += 1
                if is_recent(e):
                    kw_r[kw] += 1
    recent_n = sum(1 for e in entries if is_recent(e))
    bursts = []
    for kw in BURST_KEYWORDS:
        r = kw_r[kw]
        if r == 0:
            continue
        cs = kw_t[kw] / total if total else 0
        rs = r / recent_n if recent_n else 0
        bursts.append({"keyword": kw, "recent": r, "total": kw_t[kw],
                       "burst_score": round(rs / cs, 2) if cs > 0 else 99,
                       "recent_share": round(rs, 4)})
    bursts.sort(key=lambda b: (-b["burst_score"], -b["recent"]))

    venue_counter = Counter((", ".join(e.get("venue")) if isinstance(e.get("venue"), list) else (e.get("venue") or "")).strip() for e in entries)
    venue_counter.pop("", None)
    top_venues = [{"name": v, "papers": n} for v, n in venue_counter.most_common(15)]
    arxiv_n = sum(1 for e in entries if "arxiv" in e.get("url", ""))
    doi_n = sum(1 for e in entries if "doi.org" in e.get("url", "") or e.get("url", "").startswith("10."))

    thin = sorted(cell_counter.items(), key=lambda kv: kv[1])[:10]
    cell_recent = Counter(
        f"{e.get('category','')}/{e.get('subcategory','')}" for e in entries if is_recent(e)
    )
    whitespace = []
    for cell, ct in cell_counter.items():
        rc = cell_recent[cell]
        if ct <= 25 and rc >= 3:
            whitespace.append({"cell": cell, "total": ct, "recent": rc,
                               "recent_share": round(rc / ct, 2)})
    whitespace.sort(key=lambda w: (-w["recent_share"], -w["recent"]))

    author_counter = Counter()
    for e in entries:
        for a in e.get("authors", []) or []:
            if a:
                author_counter[a] += 1
    top_authors = [{"name": a, "papers": n} for a, n in author_counter.most_common(15)]

    stats = {
        "metadata": {
            "total_papers": total,
            "generated_date": max((e.get("date", "") for e in entries if e.get("date")), default=""),
            "taxonomy": {
                "categories": len(cats), "subcategories": len(subs),
                "total_cells": total_cells, "filled_cells": filled_cells,
                "saturation": saturation, "empty_cells": total_cells - filled_cells,
            },
            "analysis_window": {"last_12m_start": f"{cur_lo[0]:04d}-{cur_lo[1]:02d}"},
        },
        "by_category": {c: cat_counter.get(c, 0) for c in cats},
        "by_subcategory": {s: sub_counter.get(s, 0) for s in subs},
        "by_year": {y: year_counter[y] for y in sorted(year_counter, key=lambda x: (x == "unknown", x))},
        "by_cell": {c: cell_counter[c] for c in sorted(cell_counter, key=lambda c: -cell_counter[c])},
        "emerging_themes_12m": [{"keyword": b["keyword"], "papers": b["recent"]} for b in bursts[:10]],
        "momentum": momentum,
        "category_trajectory": trajectory,
        "keyword_bursts": bursts[:15],
        "source_breakdown": {"arxiv": arxiv_n, "doi": doi_n, "other": total - arxiv_n - doi_n},
        "venues": top_venues,
        "gaps": {
            "thinnest_cells": [{"cell": c, "papers": n} for c, n in thin],
            "white_space": whitespace[:10],
        },
        "top_authors": top_authors,
    }

    export = []
    for e in entries:
        export.append({k: e.get(k, "") for k in
                       ("title", "date", "url", "category", "subcategory", "authors", "abstract", "venue")})
    export.sort(key=lambda p: p.get("date", ""), reverse=True)

    pub_dates = [(e.get("date", "")[:7], e.get("category", ""), e.get("subcategory", ""))
                 for e in entries if e.get("date")]
    viz = {
        "categories": [{
            "id": c, "name": research_config.category_display(_CFG, c),
            "count": cat_counter.get(c, 0),
            "trajectory": trajectory.get(c, {}),
            "momentum": next((m for m in momentum if m["id"] == c), None),
        } for c in cats],
        "subcategories": [{"id": s, "name": research_config.subcategory_display(_CFG, s), "count": sub_counter.get(s, 0)}
                          for s in subs],
        "timeline": sorted(pub_dates),
        "venues": top_venues,
        "keyword_bursts": bursts[:15],
    }
    return stats, export, viz


def _json_dump(obj, indent):
    return json.dumps(obj, indent=indent, ensure_ascii=False) + "\n"


# Output files this generator owns (path, serialized content)
STATS_OUTPUTS = (
    # (relative path, payload-key, indent)
    ("statistics.json", "stats", 2),
    ("papers.json", "papers", 1),
    ("assets/graph_analysis.json", "viz", 1),
)


def build_outputs(stats, papers_export, viz):
    """Return {relative_path: serialized string} for every generator output."""
    payloads = {"stats": stats, "papers": papers_export, "viz": viz}
    return {
        rel: _json_dump(payloads[key], indent)
        for rel, key, indent in STATS_OUTPUTS
    }


def main():
    parser = argparse.ArgumentParser(description="Generate statistics & visualization outputs")
    parser.add_argument(
        "--check", action="store_true",
        help="Verify all outputs are up-to-date without writing (exit 1 if stale)",
    )
    args = parser.parse_args()

    with open(REPO / "papers.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    entries = data.get("papers", [])
    stats, export, viz = compute_all(entries)
    outputs = build_outputs(stats, export, viz)

    # The README corpus-statistics section is owned by this script too
    # (marker-delimited; migrated from legacy headings when needed).
    readme = REPO / "README.md"
    readme_expected = None
    if readme.exists():
        stats_md = readme_sections.render_stats_section(stats, _CFG)
        readme_expected = readme_sections.render_readme_check(
            readme.read_text(encoding="utf-8"),
            readme_sections.STATS_START, readme_sections.STATS_END,
            stats_md,
            legacy_heading=readme_sections.STATS_LEGACY_HEADING)

    if args.check:
        stale = []
        for rel in outputs:
            path = REPO / rel
            current = path.read_text(encoding="utf-8") if path.exists() else None
            if current != outputs[rel]:
                stale.append(rel)
        if readme_expected is not None and readme_expected != readme.read_text(encoding="utf-8"):
            stale.append("README.md (corpus statistics)")
        if not stale:
            print("All stats outputs are up-to-date.")
            sys.exit(0)
        print(
            "Stale outputs: " + ", ".join(stale) +
            ". Run scripts/standard_stats.py to regenerate.",
            file=sys.stderr,
        )
        sys.exit(1)

    for rel, content in outputs.items():
        path = REPO / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    print(f"Wrote statistics.json ({len(entries)} papers), papers.json, assets/graph_analysis.json")

    if readme_expected is not None:
        if readme_expected != readme.read_text(encoding="utf-8"):
            readme.write_text(readme_expected, encoding="utf-8")
            print("Updated README.md corpus statistics")
        else:
            print("README.md corpus statistics up to date")


if __name__ == "__main__":
    main()