#!/usr/bin/env python3
"""Standard landscape analyzer for a *-research corpus.

Self-contained: derives the taxonomy dynamically from papers.yaml. Produces
category growth/YoY, research aspects, year trend, venue mix, top authors,
hot & thin cells and emerging themes.

Standard pipeline mimic shared across all research repos.

Usage:
    python3 tools/landscape_analyzer.py                 # terminal report
    python3 tools/landscape_analyzer.py --json          # machine-readable
    python3 tools/landscape_analyzer.py --write-doc     # docs/research/landscape_report.md
"""

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import research_config

REPO = Path(__file__).resolve().parent.parent

THEME_KEYWORDS = [
    "reinforcement", "deep rl", "multi-agent", "agentic", "agent", "planning",
    "hierarchical", "simulation", "simulator", "world model", "decision",
    "optimization", "bayesian", "uncertainty", "transfer", "imitation",
    "offline", "memory", "retrieval", "self-supervised", "benchmark",
    "dataset", "survey", "human", "autonomous", "scalable", "federated",
    "explainab", "diffusion", "language model", "multimodal", "graph",
    "skill", "tool", "embodied", "causal", "attention",
]
# Config-driven keywords override THEME_KEYWORDS when taxonomy.yaml defines them.
_CFG = research_config.require_valid_config()
THEME_KEYWORDS = research_config.get_trend_keywords(_CFG) or THEME_KEYWORDS


def _display(kebab):
    """Display name from config, falling back to title-casing the id."""
    d = research_config.category_display(_CFG, kebab)
    if d == kebab:
        d = research_config.subcategory_display(_CFG, kebab)
    if d == kebab:
        d = kebab.replace("-", " ").replace("_", " ").title()
    return d


def load_papers():
    with open(REPO / "papers.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("papers", [])


def analyze(papers):
    now = datetime.now()
    cy, py, tp = now.year, now.year - 1, now.year - 2
    n = len(papers)

    def is_in(p, year):
        return p.get("date", "")[:4] == str(year)

    cats = sorted({p.get("category", "unknown") for p in papers})
    subs = sorted({p.get("subcategory", "unknown") for p in papers})

    cat_total = Counter(p.get("category", "unknown") for p in papers)
    cat_prev = Counter(p.get("category", "unknown") for p in papers if is_in(p, py))
    cat_2prev = Counter(p.get("category", "unknown") for p in papers if is_in(p, tp))
    cat_cur = Counter(p.get("category", "unknown") for p in papers if is_in(p, cy))

    cutoff = f"{py}-{now.month:02d}"
    recent = [p for p in papers if p.get("date", "") >= cutoff]
    recent_by_cat = Counter(p.get("category", "unknown") for p in recent)

    sub_total = Counter(p.get("subcategory", "unknown") for p in papers)
    year_total = Counter(p.get("date", "")[:4] for p in papers if p.get("date"))
    venue = Counter((", ".join(p.get("venue")) if isinstance(p.get("venue"), list) else (p.get("venue") or "")).strip() for p in papers)
    venue.pop("", None)
    arxiv_count = sum(1 for p in papers if "arxiv.org" in p.get("url", ""))

    author_counter = Counter()
    for p in papers:
        for a in p.get("authors", []):
            if a:
                author_counter[a] += 1

    rc, ac = Counter(), Counter()
    for p in papers:
        text = (p.get("title", "") + " " + p.get("abstract", "")).lower()
        for kw in THEME_KEYWORDS:
            if kw in text:
                ac[kw] += 1
    for p in recent:
        text = (p.get("title", "") + " " + p.get("abstract", "")).lower()
        for kw in THEME_KEYWORDS:
            if kw in text:
                rc[kw] += 1
    themes, rn = [], max(len(recent), 1)
    for kw in THEME_KEYWORDS:
        r, t = rc.get(kw, 0), ac.get(kw, 0)
        if r == 0:
            continue
        cs, rs = t / n, r / rn
        themes.append({"keyword": kw, "recent": r, "total": t,
                       "burst": round(rs / cs, 2) if cs else 99})
    themes.sort(key=lambda x: (-x["burst"], -x["recent"]))

    cell_counter = Counter(f"{p.get('category','?')}/{p.get('subcategory','?')}" for p in papers)

    cats_out = []
    for c in cats:
        t = cat_total.get(c, 0)
        if t == 0:
            continue
        cur, prev, prev2 = cat_cur.get(c, 0), cat_prev.get(c, 0), cat_2prev.get(c, 0)
        yoy = (cur - prev) / prev if prev else 0
        cats_out.append({
            "category": c, "name": _display(c), "total": t,
            f"y{tp}": prev2, f"y{py}": prev, f"y{cy}": cur,
            "yoy": round(yoy, 2),
            "recent_12m_share": round(recent_by_cat.get(c, 0) / max(len(recent), 1), 3),
        })
    cats_out.sort(key=lambda x: -x["total"])

    return {
        "generated": now.isoformat()[:10],
        "total_papers": n,
        "arxiv_papers": arxiv_count,
        "journal_papers": n - arxiv_count,
        "year_span": f"{min(year_total)}-{max(year_total)}" if year_total else "—",
        "years": {y: year_total[y] for y in sorted(year_total)},
        "categories": cats_out,
        "aspects": {s: sub_total.get(s, 0) for s in subs},
        "themes": themes[:15],
        "top_authors": author_counter.most_common(15),
        "top_venues": venue.most_common(10),
        "hottest_cells": sorted(cell_counter.items(), key=lambda kv: -kv[1])[:10],
        "thin_cells": sorted(cell_counter.items(), key=lambda kv: kv[1])[:10],
    }


def render_markdown(res):
    L = ["# Paper Landscape Report", "",
         f"**Generated:** {res['generated']}  ",
         f"**Corpus:** {res['total_papers']:,} papers ({res['year_span']}) | "
         f"{res['arxiv_papers']:,} arXiv preprints · {res['journal_papers']:,} journal/publisher records", "",
         "## Category Landscape", "",
         "| Category | Total | Prev Yr | This Yr | YoY | 12m Share |",
         "|----------|------:|--------:|--------:|----:|----------:|"]
    cy, py = res["generated"][:4], str(int(res["generated"][:4]) - 1)
    for c in res["categories"]:
        L.append(f"| {c['name']} | {c['total']} | {c[f'y{py}']} | {c[f'y{cy}']} | "
                 f"{c['yoy']*100:+.0f}% | {c['recent_12m_share']*100:.0f}% |")
    L += ["", "## Research Aspects", ""]
    for s, v in res["aspects"].items():
        share = v / res["total_papers"] * 100 if res["total_papers"] else 0
        L.append(f"- **{_display(s)}**: {v} papers ({share:.0f}%) {'#' * int(share / 2)}")
    L += ["", "## Year Trend", "", "| Year | Papers |", "|------|-------:|"]
    for y, v in res["years"].items():
        L.append(f"| {y} | {v} |")
    L += ["", "## Emerging Themes (12-Month Bursts)", "",
          "| Keyword | Recent | Total | Burst |", "|---------|-------:|------:|------:|"]
    for t in res["themes"][:12]:
        L.append(f"| {t['keyword']} | {t['recent']} | {t['total']} | {t['burst']}× |")
    L += ["", "## Top Venues", "", "| Venue | Papers |", "|-------|-------:|"]
    for v, c in res["top_venues"]:
        L.append(f"| {v} | {c} |")
    L += ["", "## Top Authors", "", "| Author | Papers |", "|--------|-------:|"]
    for a, c in res["top_authors"][:10]:
        L.append(f"| {a} | {c} |")
    L += ["", "## Hottest Cells", ""] + [f"- `{cell}` — {v}" for cell, v in res["hottest_cells"]]
    L += ["", "## Thin Cells (White Space)", ""] + [f"- `{cell}` — {v}" for cell, v in res["thin_cells"]]
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="Standard landscape analyzer")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--write-doc", action="store_true")
    a = ap.parse_args()

    papers = load_papers()
    res = analyze(papers)
    if a.json:
        print(json.dumps(res, indent=2, default=str))
        return
    md = render_markdown(res)
    if a.write_doc:
        path = REPO / "docs" / "research" / "landscape_report.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(md, encoding="utf-8")
        print(f"Wrote {path}\n")
    print(md)


if __name__ == "__main__":
    main()