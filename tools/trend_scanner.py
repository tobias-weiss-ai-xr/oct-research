#!/usr/bin/env python3
"""Standard trend scanner (keyword-burst + fastest-growing cells).

Self-contained: derives the taxonomy (categories / aspects) dynamically from
the repo's papers.yaml, so it works in every *-research corpus. Provides a
reusable scan() used by scripts/analysis/generate_reports.py.

Standard pipeline mimic shared across all research repos.

Usage:
    python3 tools/trend_scanner.py --months 12
    python3 tools/trend_scanner.py --months 12 --json
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

TREND_KEYWORDS = [
    "reinforcement", "deep rl", "policy", "reward", "multi-agent", "agent",
    "agentic", "opponent", "adversarial", "hierarchical", "planning",
    "simulation", "simulator", "world model", "decision", "optimization",
    "uncertainty", "bayesian", "transfer", "imitation", "offline", "memory",
    "retrieval", "learning", "self-supervised", "unsupervised", "supervised",
    "benchmark", "dataset", "survey", "human", "teaming", "autonomous",
    "real-time", "scalable", "privacy", "federated", "explainab", "generate",
    "diffusion", "language model", "multimodal", "similarity", "graph",
    "skill", "tool", "embodied", "stochastic", "causal",
]
# Config-driven keywords override TREND_KEYWORDS when taxonomy.yaml defines them.
_CFG = research_config.require_valid_config()
TREND_KEYWORDS = research_config.get_trend_keywords(_CFG) or TREND_KEYWORDS


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


def scan(papers, months, top=15):
    now = datetime.now()
    cy, cm = now.year, now.month - months
    while cm <= 0:
        cy -= 1
        cm += 12

    def is_recent(d):
        try:
            y, m = (int(x) for x in d.split("-"))
            return (y, m) >= (cy, cm)
        except (ValueError, AttributeError):
            return False

    recent_n = sum(1 for p in papers if is_recent(p.get("date", "")))
    total_n = len(papers)

    rc, tc = Counter(), Counter()
    for p in papers:
        text = (p.get("title", "") + " " + p.get("abstract", "")).lower()
        for kw in TREND_KEYWORDS:
            if kw in text:
                tc[kw] += 1
                if is_recent(p.get("date", "")):
                    rc[kw] += 1

    trends = []
    for kw in TREND_KEYWORDS:
        r, t = rc.get(kw, 0), tc.get(kw, 0)
        if r == 0:
            continue
        corpus_share = t / total_n if total_n else 0
        recent_share = r / recent_n if recent_n else 0
        burst = recent_share / corpus_share if corpus_share > 0 else 99
        trends.append({"keyword": kw, "recent_papers": r, "total_papers": t,
                       "burst_score": round(burst, 1)})
    trends.sort(key=lambda x: (-x["burst_score"], -x["recent_papers"]))

    cell_t, cell_r = Counter(), Counter()
    for p in papers:
        c = (p.get("category", "?"), p.get("subcategory", "?"))
        cell_t[c] += 1
        if is_recent(p.get("date", "")):
            cell_r[c] += 1
    growth = []
    for cell, t in cell_t.items():
        r = cell_r.get(cell, 0)
        if r == 0 or t == 0:
            continue
        growth.append({"cell": f"{cell[0]}/{cell[1]}", "recent": r, "total": t,
                       "recent_share": round(r / t, 2)})
    growth.sort(key=lambda x: -x["recent_share"])

    return {"cutoff": f"{cy}-{cm:02d}", "recent_papers": recent_n,
            "trends": trends[:top], "growing_cells": growth[:top]}


def main():
    ap = argparse.ArgumentParser(description="Standard corpus trend scanner")
    ap.add_argument("--months", type=int, default=6)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    papers = load_papers()
    result = scan(papers, a.months, top=a.top)
    if a.json:
        print(json.dumps(result, indent=2))
        return

    print(f"\n=== Research Trends (last {a.months} months, since {result['cutoff']}) ===")
    print(f"Recent papers: {result['recent_papers']} of {len(papers)}\n")
    print("🔥 TOP KEYWORD BURSTS (recent share vs corpus share)")
    print("-" * 70)
    for t in result["trends"]:
        bar = "#" * min(40, int(t["burst_score"] * 2))
        print(f"{t['keyword']:<26} {t['recent_papers']:>4}/ {t['total_papers']:<5} burst={t['burst_score']:<5}{bar}")
    print("\n📈 FASTEST-GROWING CELLS")
    print("-" * 70)
    for g in result["growing_cells"]:
        print(f"{g['cell']:<46} {g['recent']:>3}/{g['total']:<4} ({g['recent_share']*100:.0f}% recent)")


if __name__ == "__main__":
    main()