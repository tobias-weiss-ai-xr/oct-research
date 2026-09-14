#!/usr/bin/env python3
"""Generate README.md and docs/papers.json from papers.yaml.

Generic for any *-research corpus: categories/subcategories and their display
names come from config/taxonomy.yaml (via research_config).

Usage:
    python3 scripts/generate_readme.py
    python3 scripts/generate_readme.py --check   # CI: fail if out of date
"""

import argparse
import json
import sys
from pathlib import Path

import yaml

import readme_sections
import research_config


def generate_readme(papers, readme_path, cfg, check_mode=False):
    readme_text = readme_path.read_text(encoding="utf-8")
    content = readme_sections.render_paper_list(papers, cfg)

    # Marker-delimited replacement (handles migration from legacy headers
    # and gracefully skips repos whose README deliberately has no paper list).
    new_readme, found = readme_sections.replace_section(
        readme_text,
        readme_sections.PAPERLIST_START, readme_sections.PAPERLIST_END,
        content,
        legacy_heading=readme_sections.PAPERLIST_LEGACY_HEADING)

    if not found:
        # No paper-list section and no legacy heading: this repo dropped the
        # paper list from its README (e.g. it lives on the GitHub Pages site).
        # Do NOT hard-fail — just leave the README untouched and carry on.
        print("README.md has no paper-list section — README left untouched "
              "(docs/papers.json is still written).")
        return

    if check_mode:
        if new_readme == readme_text:
            print("README.md is up-to-date.")
            sys.exit(0)
        else:
            print(
                "README.md is out-of-date. Run generate_readme.py to update.",
                file=sys.stderr,
            )
            sys.exit(1)

    readme_path.write_text(new_readme, encoding="utf-8")
    print(f"Generated {readme_path}")


def generate_json(papers, json_path):
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps({"papers": papers}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Generated {json_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate README.md and papers.json from papers.yaml"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if README is up-to-date (exit 1 if not)",
    )
    parser.add_argument(
        "--skip-json", action="store_true", help="Skip generating papers.json"
    )
    args = parser.parse_args()

    base = Path(__file__).parent.parent
    papers_yaml = base / "papers.yaml"
    readme_path = base / "README.md"
    json_path = base / "docs" / "papers.json"

    papers = research_config.load_papers(papers_yaml)
    cfg = research_config.require_valid_config()

    generate_readme(papers, readme_path, cfg, check_mode=args.check)

    if not args.check and not args.skip_json:
        generate_json(papers, json_path)


if __name__ == "__main__":
    main()
