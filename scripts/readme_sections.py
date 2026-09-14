#!/usr/bin/env python3
"""Marker-delimited, pipeline-owned README sections.

Sections of README.md that are derived from ``papers.yaml`` / config are
wrapped in invisible HTML-comment markers so a script can regenerate *just
that section* without touching the rest of the file (intro, prose, links,
citation, …):

    <!-- BEGIN CORPUS STATISTICS --> … <!-- END CORPUS STATISTICS -->
        owned by scripts/standard_stats.py
    <!-- BEGIN PAPER LIST --> … <!-- END PAPER LIST -->
        owned by scripts/generate_readme.py

This is the structural fix for the "stale README" quirk: README sections are
never maintained by hand, and the scripts no longer depend on fragile heading
matches (e.g. "## 📚 Paper list") or hard-fail when a repo deliberately drops
a section.  Everything outside the markers is user-owned prose and is left
untouched on every run.

Backwards compatibility: if the markers are missing but the legacy plain Markdown
heading still exists (``## 📊 Corpus Statistics`` / ``## 📚 Paper list``), the
old section is migrated in place to a marker-delimited one (idempotent), so
existing repos upgrade cleanly on their next pipeline run.
"""

import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ── markers ──────────────────────────────────────────────────────────────────
STATS_START = "<!-- BEGIN CORPUS STATISTICS -->"
STATS_END = "<!-- END CORPUS STATISTICS -->"
PAPERLIST_START = "<!-- BEGIN PAPER LIST -->"
PAPERLIST_END = "<!-- END PAPER LIST -->"

# Legacy plain-Markdown headings used for one-time migration (markers absent).
STATS_LEGACY_HEADING = "## 📊 Corpus Statistics"
PAPERLIST_LEGACY_HEADING = "## 📚 Paper list"

# Headings a missing section is inserted before, in priority order.
_INSERT_ANCHORS = ["## 📖 Citation", "## 📄 License", "## 📋 Appendix"]


# ── section editing ──────────────────────────────────────────────────────────
def find_section(text, start_marker, end_marker):
    """Return (start_idx, end_idx) of a marker-delimited section (inclusive of
    both markers), or (None, None) when either marker is missing."""
    si = text.find(start_marker)
    if si == -1:
        return None, None
    ei = text.find(end_marker, si)
    if ei == -1:
        return None, None
    return si, ei + len(end_marker)


def _block(start_marker, end_marker, content):
    return f"{start_marker}\n\n{content.strip()}\n\n{end_marker}"


def replace_section(text, start_marker, end_marker, content, legacy_heading=None):
    """Replace an EXISTING marker-delimited section in place.

    Args:
        text: full README text.
        start_marker / end_marker: HTML-comment markers.
        content: new section body (without markers).
        legacy_heading: optional legacy plain-Markdown heading.  When the
            markers are absent but this heading exists, the old section
            (heading .. next ``## `` heading) is replaced in place so existing
            READMEs migrate without duplicating the section.

    Returns:
        (new_text, found): ``found`` is True when the section was located
        (via markers or legacy heading) and replaced.  When neither exists,
        the text is returned unchanged with ``found=False`` — callers decide
        whether to insert or skip.
    """
    block = _block(start_marker, end_marker, content)
    si, ei = find_section(text, start_marker, end_marker)
    if si is not None:
        return text[:si] + block + text[ei:], True

    if legacy_heading:
        s = text.find(legacy_heading)
        if s != -1:
            e = text.find("\n## ", s + len(legacy_heading))
            if e == -1:
                e = len(text)
            return text[:s] + block + "\n" + text[e:], True

    return text, False


def insert_section(text, start_marker, end_marker, content):
    """Insert a section block at a sensible spot (before citation/license)."""
    block = _block(start_marker, end_marker, content)
    for anchor in _INSERT_ANCHORS + ["## "]:
        i = text.find(anchor)
        if i != -1:
            return text[:i] + block + "\n\n" + text[i:]
    return text.rstrip() + "\n\n" + block + "\n"


def upsert_readme_section(readme_path, start_marker, end_marker, content,
                          legacy_heading=None, insert_if_missing=True):
    """Regenerate one marker-delimited section of README.md in place.

    Returns True when the file changed, False when it was already up-to-date.
    Missing READMEs are left alone (section is optional).  When the section is
    absent but ``insert_if_missing`` is set, it is inserted at a sensible spot.
    """
    readme_path = Path(readme_path)
    if not readme_path.exists():
        return False
    current = readme_path.read_text(encoding="utf-8")
    new, found = replace_section(current, start_marker, end_marker, content,
                                 legacy_heading=legacy_heading)
    if not found and insert_if_missing:
        new = insert_section(current, start_marker, end_marker, content)
    if new == current:
        return False
    readme_path.write_text(new, encoding="utf-8")
    return True


def render_readme_check(readme_text, start_marker, end_marker, content,
                        legacy_heading=None, insert_if_missing=True):
    """Return the README text as it SHOULD look after regeneration.

    Used by ``--check`` modes to detect staleness without writing anything.
    ``insert_if_missing`` controls whether an absent section counts as "should
    be inserted" (stats output) or "intentionally absent" (paper list).
    """
    new, found = replace_section(readme_text, start_marker, end_marker, content,
                                 legacy_heading=legacy_heading)
    if not found and insert_if_missing:
        new = insert_section(readme_text, start_marker, end_marker, content)
    return new


# ── rendering helpers ────────────────────────────────────────────────────────
def _bar(count, spread, width=12):
    """Fixed-width ASCII/unicode progress bar (12 cells by default)."""
    if count <= 0:
        return "░" * width
    filled = max(1, min(width, round(count / spread * width)))
    return "█" * filled + "░" * (width - filled)


def render_stats_section(stats, cfg):
    """Render the ``## 📊 Corpus Statistics`` section from statistics.json data.

    Everything under this heading is regenerated by standard_stats.py on every
    run — nothing here is maintained by hand.
    """
    md = stats.get("metadata", {})
    total = md.get("total_papers", 0)
    n_cats = (md.get("taxonomy", {}) or {}).get("categories", 0)
    src = stats.get("source_breakdown", {})
    arxiv_n = src.get("arxiv", 0)

    lines = ["## 📊 Corpus Statistics", ""]
    src_pct = round(arxiv_n / total * 100) if total else 0
    lines.append(f"**{total} papers** across **{n_cats} categories**.  ")
    if arxiv_n:
        lines.append(f"Sources: **arXiv** {arxiv_n} ({src_pct}%).  ")
    pages = (cfg.get("topic") or {}).get("github_pages", "").strip()
    if pages:
        lines.append(f"Full paper list: [GitHub Pages site]({pages}).")
    lines.append("")

    # Top categories (descending by paper count)
    by_cat = stats.get("by_category", {})
    if by_cat:
        recent_map = {m.get("id"): m.get("recent", 0) for m in stats.get("momentum", [])}
        ordered = sorted(by_cat.items(), key=lambda kv: -kv[1])
        spread = max(v for _, v in ordered) or 1
        lines.append("### Top categories")
        lines.append("")
        lines.append("| Category | Papers | Recent | |")
        lines.append("|----------|--------|--------|-|")
        for cid, n in ordered:
            lines.append(f"| {cid} | **{n}** | {recent_map.get(cid, 0)} | {_bar(n, spread)} |")
        lines.append("")

    # By year
    by_year = {y: n for y, n in stats.get("by_year", {}).items() if y and y != "unknown"}
    if by_year:
        spread = max(by_year.values()) or 1
        lines.append("### By year")
        lines.append("")
        lines.append("| Year | Papers | |")
        lines.append("|------|--------|-|")
        for y in sorted(by_year):
            lines.append(f"| {y} | {by_year[y]} | {_bar(by_year[y], spread)} |")
        lines.append("")

    # Momentum
    momentum = stats.get("momentum", [])
    if momentum:
        lines.append("### Momentum (hottest categories)")
        lines.append("")
        lines.append("| Category | Total | Rate | Recent | Score |")
        lines.append("|----------|-------|------|--------|-------|")
        for m in momentum:
            share = m.get("recent_share", 0) or 0
            lines.append(
                f"| {m.get('name') or m.get('id', '')} | {m.get('total', 0)} | "
                f"{m.get('papers_per_month', 0):.1f}/mo | {round(share * 100)}% | "
                f"{round(m.get('score', 0))} |"
            )
        lines.append("")

    # Trending keywords
    bursts = stats.get("keyword_bursts", [])[:8]
    if bursts:
        lines.append("### Trending keywords")
        lines.append("")
        lines.append("| Keyword | Papers | Burst |")
        lines.append("|---------|--------|-------|")
        for b in bursts:
            lines.append(f"| {b.get('keyword', '')} | {b.get('recent', b.get('total', 0))} | "
                         f"{b.get('burst_score', '')} |")
        lines.append("")

    # Top venues
    venues = [v for v in stats.get("venues", []) if v.get("name")]
    if venues:
        lines.append("### Top venues")
        lines.append("")
        lines.append("| Venue | Papers |")
        lines.append("|-------|--------|")
        for v in venues[:10]:
            lines.append(f"| {v.get('name')} | {v.get('papers', 0)} |")
        lines.append("")

    # Research gaps
    thin = stats.get("gaps", {}).get("thinnest_cells", [])[:5]
    if thin:
        lines.append("### Research gaps (thinnest cells)")
        lines.append("")
        lines.append("| Cell | Papers |")
        lines.append("|------|--------|")
        for g in thin:
            lines.append(f"| `{g.get('cell', '')}` | {g.get('papers', 0)} |")
        lines.append("")

    lines.append(f"*Generated {datetime.now():%Y-%m} by `scripts/standard_stats.py`.*")
    return "\n".join(lines)


def render_paper_list(papers, cfg):
    """Render the ``## 📚 Paper list`` section grouped by taxonomy + year.

    Owned by scripts/generate_readme.py; mirrors the classic layout so repos
    keep their paper list exactly as before (TOC + category/subcategory/year
    groups), just marker-delimited now.
    """
    lines = ["## 📚 Paper list", ""]

    cats = cfg.get("taxonomy", {}).get("categories", [])
    subs = cfg.get("taxonomy", {}).get("subcategories", [])

    # Emoji TOC
    for cat in cats:
        cat_display = cat.get("display", cat["id"])
        cat_anchor = cat_display.lower().replace(" ", "-")
        lines.append(f"- [📚 {cat_display}](#{cat_anchor})")
        for sub in subs:
            group = [p for p in papers if p["category"] == cat["id"] and p["subcategory"] == sub["id"]]
            if not group:
                continue
            sub_display = sub.get("display", sub["id"])
            sub_anchor = sub_display.lower().replace(" ", "-")
            lines.append(f"  - [{sub_display}](#{sub_anchor})")
    lines.append("")

    for cat in cats:
        cat_display = cat.get("display", cat["id"])
        lines.append(f"### {cat_display}")
        lines.append("")

        for sub in subs:
            group = [p for p in papers if p["category"] == cat["id"] and p["subcategory"] == sub["id"]]
            if not group:
                continue

            sub_display = sub.get("display", sub["id"])
            lines.append(f"#### {sub_display}")
            lines.append("")

            # Group by year
            year_groups = defaultdict(list)
            for p in group:
                year_groups[p["date"][:4]].append(p)

            for year in sorted(year_groups.keys(), reverse=True):
                lines.append(f"##### {year}")
                lines.append("")

                sorted_papers = sorted(year_groups[year], key=lambda p: p["date"], reverse=True)
                for p in sorted_papers:
                    y = p["date"][:4]
                    title = p["title"]
                    url = p["url"]
                    venue = p.get("venue", "")
                    code_url = p.get("code_url", "")
                    project_url = p.get("project_url", "")

                    entry = f"- [{y}] **{title}**"
                    if venue:
                        entry += f" *{venue}*"
                    entry += f" [[paper]({url})]"
                    if code_url:
                        entry += f" [[code]({code_url})]"
                    if project_url:
                        entry += f" [[project]({project_url})]"
                    lines.append(entry)

                lines.append("")

            lines.append("[⬆ Back to top](#paper-list)")
            lines.append("")

    return "\n".join(lines)
