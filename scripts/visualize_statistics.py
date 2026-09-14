#!/usr/bin/env python3
"""Standard visualize_statistics.py for a *-research corpus.

ASCII fallback bar chart (no matplotlib requirement) + optional matplotlib PNG.
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def main():
    stats = json.loads((REPO / "statistics.json").read_text(encoding="utf-8"))
    by_cat = stats.get("by_category", {})
    items = [(str(k).replace("-", " ").title(), v)
             for k, v in sorted(by_cat.items(), key=lambda kv: -kv[1])]
    if not items:
        print("No category data.")
        return
    max_v = max((v for _, v in items), default=1)
    scale = 40 / max_v if max_v else 1
    print("Papers per category:\n")
    for label, v in items:
        print(f"  {label:<38} {'█' * int(v * scale)} {v}")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        OUT = REPO / "assets" / "visualizations"
        OUT.mkdir(parents=True, exist_ok=True)
        fig, ax = plt.subplots(figsize=(9, max(4, len(items) * 0.45)))
        ax.barh([l for l, _ in items], [v for _, v in items], color="#4C6EF5")
        ax.set_title("Papers per category")
        ax.set_xlabel("Papers")
        ax.grid(axis="x", alpha=0.3)
        fig.tight_layout()
        fig.savefig(OUT / "category_distribution.png", dpi=140)
        print(f"\nWrote {OUT / 'category_distribution.png'}")
    except Exception:
        print("\n(matplotlib not available — ran ASCII chart only)")


if __name__ == "__main__":
    main()