#!/usr/bin/env python3
"""feedback_concepts.py — close the loop: feed graph analysis back into seeds.

Minimal, portable, deterministic. Reads concept_graph_analysis.json (from
analyze_concept_graph.py) and proposes curated concept seeds to add to
config/concepts.yaml:

  * bridge concepts — high betweenness: cross-cutting integration hubs that
    connect otherwise separate strands (prime for integrative synthesis).
  * gap concepts    — meaningful (df >= --gap-min-df) but barely connected
    (degree <= --gap-max-degree): under-explored white space.

Taxonomy categories are skipped (they are already a structural source), and
existing seeds are preserved. Use --dry-run to preview; otherwise it rewrites
config/concepts.yaml (keeping its header comment). Run it after the analysis
step, review the diff, commit.

    python3 tools/feedback_concepts.py --analysis concept_graph_analysis.json \
        --concepts config/concepts.yaml
"""
import argparse
import json
import sys
from pathlib import Path


def load_yaml_list(path):
    """Return (header_text_before_concepts, [current seed strings])."""
    text = Path(path).read_text(encoding="utf-8")
    head, _, tail = text.partition("concepts:")
    cur = []
    for line in tail.splitlines():
        line = line.strip()
        if line.startswith("- "):
            cur.append(line[2:].strip())
    return head, cur


def write_yaml(path, head, items):
    out = head.rstrip("\n") + "\nconcepts:\n"
    for it in sorted(set(items), key=str.lower):
        out += f"  - {it}\n"
    Path(path).write_text(out, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Feed graph analysis back into concept seeds.")
    ap.add_argument("--analysis", default="concept_graph_analysis.json")
    ap.add_argument("--concepts", default="config/concepts.yaml")
    ap.add_argument("--min-betweenness", type=float, default=25.0,
                    help="betweenness threshold for bridge concepts")
    ap.add_argument("--min-pagerank", type=float, default=0.01,
                    help="min PageRank for a bridge concept to count as a real theme "
                         "(filters out high-betweenness boilerplate bigrams)")
    ap.add_argument("--gap-max-degree", type=int, default=2,
                    help="degree at/below which a node is 'isolated'")
    ap.add_argument("--gap-min-df", type=int, default=3,
                    help="min document frequency for an isolated node to count as a gap")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(args.analysis, encoding="utf-8") as f:
        a = json.load(f)
    head, cur = load_yaml_list(args.concepts)
    cur_lc = {c.lower() for c in cur}

    bridges, gaps = [], []
    for n in a["nodes"]:
        term, kind = n["term"], n.get("kind")
        if kind == "taxonomy":
            continue
        if term.lower() in cur_lc:
            continue
        if n.get("betweenness", 0) >= args.min_betweenness and \
                n.get("pagerank", 0) >= args.min_pagerank:
            bridges.append(term)
        elif n.get("degree", 0) <= args.gap_max_degree and n.get("df", 0) >= args.gap_min_df:
            gaps.append(term)

    added = sorted(set(bridges) | set(gaps), key=str.lower)
    print(f"Bridge concepts (high betweenness): {bridges}")
    print(f"Gap concepts (meaningful but isolated): {gaps}")
    print(f"New seeds to add: {added}")
    if args.dry_run:
        print("(dry-run — not written)")
        return
    if not added:
        print("Nothing to add — config/concepts.yaml already covers the analysis.")
        return
    write_yaml(args.concepts, head, cur + added)
    print(f"Wrote {args.concepts} ({len(cur)} -> {len(cur) + len(added)} seeds)")


if __name__ == "__main__":
    main()
