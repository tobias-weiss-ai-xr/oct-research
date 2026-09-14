#!/usr/bin/env python3
"""Standard brief generator for a *-research corpus.

Search the corpus by topic keywords and print (or write) a ready-to-write
article brief. Self-contained taxonomy discovery.

Standard pipeline mimic shared across all research repos.

Usage:
    python3 tools/brief_generator.py "topic words" --papers 5
    python3 tools/brief_generator.py "topic words" --as-doc
"""

import argparse
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import research_config

REPO = Path(__file__).resolve().parent.parent

_CFG = research_config.require_valid_config()

STOP = {"for", "in", "the", "and", "with", "of", "on", "to", "a", "an"}


def _display(kebab):
    """Display name from config, falling back to title-casing the id."""
    d = research_config.category_display(_CFG, kebab)
    if d == kebab:
        d = research_config.subcategory_display(_CFG, kebab)
    if d == kebab:
        d = kebab.replace("-", " ").replace("_", " ").title()
    return d


def slugify(topic):
    return re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_") or "brief"


def load_papers():
    with open(REPO / "papers.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("papers", [])


def find_papers(papers, topic):
    terms = [t for t in topic.lower().split() if t not in STOP]
    scored = []
    for p in papers:
        hay = " ".join([p.get("title", ""), p.get("category", ""),
                        p.get("subcategory", ""), p.get("abstract", "")]).lower()
        m = sum(1 for t in terms if t in hay)
        if m:
            scored.append((m, p))
    scored.sort(key=lambda x: -x[0])
    return [p for _, p in scored]


def main():
    ap = argparse.ArgumentParser(description="Standard brief generator")
    ap.add_argument("topic")
    ap.add_argument("--papers", type=int, default=5)
    ap.add_argument("--as-doc", action="store_true")
    a = ap.parse_args()

    papers = load_papers()
    hits = find_papers(papers, a.topic)[: a.papers]

    lines = [f"# Article Brief: {a.topic}\n"]
    if not hits:
        lines.append("No corpus papers matched. Consider expanding the corpus.")
    for p in hits:
        cat = f"{_display(p.get('category',''))} / {_display(p.get('subcategory',''))}"
        lines.append(f"- **{p.get('title','')}** ({cat}) — {p.get('date','')} — {p.get('url','')}")
        if p.get("abstract"):
            lines.append(f"  {p['abstract'][:400].rsplit(' ', 1)[0]}…\n")

    print("\n".join(lines))

    if a.as_doc:
        out = REPO / "docs" / "topics" / f"brief_{slugify(a.topic)}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines), encoding="utf-8")
        print(f"\nWrote {out}")


if __name__ == "__main__":
    main()