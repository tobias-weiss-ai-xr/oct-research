#!/usr/bin/env python3
"""Standard topic planner for a *-research corpus.

Ranks categories by paper count + recent (12-month) activity and writes
docs/topics/ARTICLE_TOPICS.md. Self-contained taxonomy discovery.

Standard pipeline mimic shared across all research repos.

Usage:
    python3 tools/topic_planner.py --top 10
"""

import argparse
import collections
import json
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent


def _display(kebab):
    return kebab.replace("-", " ").replace("_", " ").title()


def load_papers():
    with open(REPO / "papers.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("papers", [])


def load_bridge_scores() -> dict:
    """category_id -> normalized betweenness (0..1) from concept_graph_analysis.json.

    Mirrors tools/research_gap_analyzer.py: the concept graph's taxonomy nodes
    carry a betweenness score (how strongly that category bridges separate
    strands). Returns {} when the analysis file or taxonomy is absent, so the
    planner still works standalone (bridge = 0).
    """
    path = REPO / "concept_graph_analysis.json"
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            a = json.load(f)
    except Exception:
        return {}
    label_to_id = {}
    try:
        with open(REPO / "config" / "taxonomy.yaml", encoding="utf-8") as f:
            tcfg = yaml.safe_load(f) or {}
        for c in tcfg.get("taxonomy", {}).get("categories", []):
            label_to_id[c.get("display")] = c.get("id")
    except Exception:
        pass
    betas = {}
    for n in a.get("nodes", []):
        if n.get("kind") == "taxonomy":
            cid = label_to_id.get(n.get("term"))
            if cid is not None:
                betas[cid] = n.get("betweenness", 0.0)
    if not betas:
        return {}
    mx = max(betas.values()) or 1.0
    return {cid: b / mx for cid, b in betas.items()}


def _year(p):
    d = p.get("date", "")
    return d[:4] if isinstance(d, str) and len(d) >= 4 and d[:4].isdigit() else ""


def main():
    ap = argparse.ArgumentParser(description="Standard topic planner")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--bridge-weight", type=float, default=30.0,
                    help="weight of the cross-cutting bridge signal from the "
                         "concept graph (default 30; set 0 to disable)")
    a = ap.parse_args()

    papers = load_papers()
    by_cat = collections.Counter(p.get("category", "unknown") for p in papers)
    years = sorted({y for y in (_year(p) for p in papers) if y})
    latest = years[-1] if years else "0000"
    cut = str(int(latest) - 1)
    recent = collections.Counter(
        p.get("category", "unknown") for p in papers if _year(p) >= cut
    )
    rn = sum(1 for p in papers if _year(p) >= cut)
    bridge_scores = load_bridge_scores()

    rows = []
    for c, n in by_cat.items():
        r = recent.get(c, 0)
        score = n + (r / max(rn, 1)) * 10
        bridge = bridge_scores.get(c, 0.0)
        opportunity = round(score + a.bridge_weight * bridge, 2)
        rows.append({"category": c, "papers": n, "recent": r,
                     "score": round(score, 2), "bridge": round(bridge, 3),
                     "opportunity": opportunity})
    rows.sort(key=lambda x: -x["opportunity"])

    top = rows[: a.top]
    print(f"Top {len(top)} content opportunities (evidence + bridge):\n")
    for i, r in enumerate(top, 1):
        print(f"{i:>2}. {_display(r['category'])} (papers={r['papers']}, "
              f"recent={r['recent']}, evidence={r['score']}, "
              f"bridge={r['bridge']:.2f}, opportunity={r['opportunity']})")

    md = ["# Article Topics (auto-generated)\n",
          "Ranked by content opportunity = evidence (paper count + recent "
          "activity) + the concept graph's cross-cutting bridge signal "
          "(how strongly the category connects separate research strands). "
          "Bridge topics are integrative content angles.\n"]
    bridge_top = [r for r in rows if r["bridge"] >= 0.5][: a.top]
    if bridge_top:
        md.append("\n## Integrative bridge topics\n")
        md.append("High-betweenness categories — cross-cutting content angles "
                  "that connect separate strands:\n")
        for r in bridge_top:
            md.append(f"- **{_display(r['category'])}** — bridge {r['bridge']:.2f} "
                      f"({r['papers']} papers)\n")
    for r in top:
        md += [f"\n## {_display(r['category'])}\n",
               f"Evidence-based topic: {r['papers']} curated papers, "
               f"{r['recent']} in the last 12 months. "
               f"Bridge signal: {r['bridge']:.2f}; opportunity: {r['opportunity']}.\n"]
    out = REPO / "docs" / "topics" / "ARTICLE_TOPICS.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(md), encoding="utf-8")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()