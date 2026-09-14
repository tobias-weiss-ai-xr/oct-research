#!/usr/bin/env python3
"""Shared utilities for repo discovery fetchers (GitHub, GitLab, Codeberg, …).

Every ``fetch_*_repos.py`` script imports from this module so that relevance
filtering, subcategory classification, YAML I/O, and text helpers live in
one place.

Usage (import only — not runnable directly):
    from repos_common import load_topic_signals, is_relevant_repo, ...
"""

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

__all__ = [
    "REPOS_YAML",
    "DEFAULT_USER_AGENT",
    "http_get_with_retry",
    "_norm",
    "_tokenize",
    "_word_re",
    "load_topic_signals",
    "is_relevant_repo",
    "DEFAULT_SUBCATEGORY_RULES",
    "SUBCATEGORY_FALLBACK",
    "classify_subcategory",
    "_yaml_str",
    "format_yaml_entry",
    "load_existing_repos",
    "append_repos",
    "normalize_entry",
]

BASE = Path(__file__).resolve().parent.parent.parent
REPOS_YAML = BASE / "repos.yaml"

DEFAULT_USER_AGENT = "Research-Corpus/1.0 (mailto:research@tobias-weiss-ai-xr.de)"


def http_get_with_retry(session, url, *, params=None, timeout=30,
                        max_retries=4, headers=None, rate_limit_wait=60,
                        sleep_fn=None):
    """GET a URL with consistent backoff + rate-limit handling.

    Centralises the retry / ``Retry-After`` / 429 / 5xx / timeout / connection
    handling that used to be duplicated in every fetcher.  Returns the
    ``requests.Response`` on success, or ``None`` after exhausting retries.

    Backoff policy:
      - 429: honour ``Retry-After`` header (capped at ``rate_limit_wait``),
        else wait ``rate_limit_wait``.
      - 5xx / timeout / connection error: exponential backoff
        (2s, 4s, 8s, … capped at 30s).

    ``sleep_fn`` may be injected for testing (defaults to ``time.sleep``).
    """
    import time

    import requests

    sleep = sleep_fn or time.sleep

    for attempt in range(max_retries):
        try:
            resp = session.get(url, params=params, timeout=timeout, headers=headers)
        except requests.exceptions.Timeout:
            wait = min(2 ** (attempt + 1), 30)
            print(f"    timeout, waiting {wait}s (attempt {attempt+1}/{max_retries})",
                  flush=True)
            sleep(wait)
            continue
        except requests.exceptions.ConnectionError:
            wait = min(2 ** (attempt + 1), 30)
            print(f"    connection error, waiting {wait}s (attempt {attempt+1}/{max_retries})",
                  flush=True)
            sleep(wait)
            continue

        if resp.status_code == 429:
            reset = _retry_after_seconds(resp, rate_limit_wait)
            print(f"    rate limit (429), waiting {reset}s (attempt {attempt+1}/{max_retries})",
                  flush=True)
            sleep(reset)
            continue

        if resp.status_code >= 500:
            wait = min(2 ** (attempt + 1), 30)
            print(f"    server {resp.status_code}, waiting {wait}s "
                  f"(attempt {attempt+1}/{max_retries})", flush=True)
            sleep(wait)
            continue

        return resp
    return None


def _retry_after_seconds(resp, default_wait):
    """Parse the Retry-After header, capped at ``default_wait`` seconds."""
    import time

    raw = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
    if raw is None:
        return default_wait
    raw = raw.strip()
    try:
        if raw.isdigit():
            secs = int(raw)
        else:
            # HTTP-date — compute seconds until then, bounded.
            from email.utils import parsedate_to_datetime
            when = parsedate_to_datetime(raw)
            secs = int(when.timestamp() - time.time())
        return max(1, min(secs, default_wait))
    except Exception:
        return default_wait


# ── Text helpers ─────────────────────────────────────────────────────────

def _norm(text):
    """Lowercase and collapse whitespace/hyphens/slashes."""
    return re.sub(r"[\s\-/]+", " ", text.lower())


def _tokenize(text):
    """Split text into individual normalized tokens."""
    return _norm(text).split()


def _word_re(tokens):
    """Build a regex that matches tokens at word boundaries.

    Multi-word tokens (containing spaces) match with a leading ``\\b`` only,
    following the _word_re fix: ``re.escape`` in Python 3.11+ escapes internal
    spaces, so we escape each word individually and join with a literal space.
    No trailing ``\\b`` for multi-word tokens to allow plural/fuzzy matches
    (e.g. "supply chains" matches "supply chain").
    """
    parts = []
    for t in tokens:
        words = _norm(t).split(" ")
        escaped = [re.escape(w) for w in words]
        if len(escaped) == 1:
            parts.append(r"\b" + escaped[0] + r"\b")
        else:
            parts.append(r"\b" + " ".join(escaped))
    return re.compile(r"|".join(parts), re.I)


# ── Relevance filtering ──────────────────────────────────────────────────

# Generic stop tokens that don't signal topic relevance
_SKIP_TOKENS = {
    "research", "corpus", "study", "review", "analysis", "paper", "approach",
    "system", "method", "model", "based", "using", "data", "framework",
    "novel", "proposed", "new", "survey", "topic", "skeleton", "source",
}


def load_topic_signals(cfg):
    """Extract relevance signals from the topic config.

    Builds a set of normalized keyword tokens from:
      1. ``topic.name``, ``topic.short``, ``topic.description``
      2. Category and subcategory IDs from the taxonomy
      3. Optional ``repo_signals`` list in taxonomy.yaml (generic, shared by all
         repo fetchers — supersedes the older ``github_signals`` key)

    These tokens are compiled into a regex used by ``is_relevant_repo()`` to
    gate out repos unrelated to the research topic.
    """
    tokens = set()

    # From topic metadata
    topic = cfg.get("topic", {})
    for key in ("name", "short", "description"):
        val = topic.get(key, "")
        if val:
            tokens.update(_tokenize(val))

    # From taxonomy IDs
    for cat in cfg.get("taxonomy", {}).get("categories", []):
        tokens.add(cat.get("id", "").lower())
    for sub in cfg.get("taxonomy", {}).get("subcategories", []):
        tokens.add(sub.get("id", "").lower())

    # Explicit signal list — prefer generic ``repo_signals``, fall back to ``github_signals``
    explicit = cfg.get("repo_signals", []) or cfg.get("github_signals", [])
    for sig in explicit:
        tokens.update(_tokenize(sig))

    return sorted(t for t in tokens if len(t) >= 3 and t not in _SKIP_TOKENS)


def is_relevant_repo(name, description, topics, signal_re):
    """Gate out repos unrelated to the research topic.

    Uses a pre-compiled regex from ``load_topic_signals()``.  Passes when
    no signals are configured (empty pattern).
    """
    if not signal_re or signal_re.pattern in (r"\b\b", r"(?!)"):
        return True
    text = _norm(f"{name} {description} {' '.join(topics)}")
    return bool(signal_re.search(text))


# ── Subcategory classification ────────────────────────────────────────────

DEFAULT_SUBCATEGORY_RULES = [
    ("review", ["survey", "benchmark", "comparison", "awesome", "collection",
                "curated", "list", "catalogue", "directory"], True),
    ("theory", ["framework", "specification", "standard", "rfc", "architecture",
                "model", "ontology", "taxonomy"], False),
    ("application", ["cli", "tool", "scanner", "analyzer", "detector", "checker",
                     "linter", "parser", "processor", "converter", "engine"], False),
    ("development", ["sdk", "library", "api", "client", "wrapper", "binding",
                      "plugin", "extension", "module", "package"], False),
    ("method", ["template", "boilerplate", "starter", "example", "demo",
                "playground", "tutorial", "cookbook", "guide", "examples"], False),
    ("systems", ["platform", "orchestrator", "operator", "controller", "runtime",
                 "daemon", "service", "server", "broker", "gateway"], False),
    ("evaluation", ["benchmark", "test-suite", "testbed", "evaluation",
                    "metrics", "dataset", "corpus", "baseline"], False),
]
SUBCATEGORY_FALLBACK = "application"


def classify_subcategory(name, description, topics, cfg):
    """Assign subcategory from repo metadata + taxonomy config.

    First tries to match taxonomy subcategory IDs in the repo text, then
    falls back to keyword heuristics.
    """
    text = f"{name} {description} {' '.join(topics)}".lower()
    name_lower = name.lower()

    # Try matching subcategory IDs directly
    for sub in cfg.get("taxonomy", {}).get("subcategories", []):
        sub_id = sub.get("id", "")
        if sub_id and sub_id in text:
            return sub_id

    # Heuristic rules
    for subcat, keywords, title_only in DEFAULT_SUBCATEGORY_RULES:
        haystack = name_lower if title_only else text
        for kw in keywords:
            if kw in haystack:
                return subcat

    return SUBCATEGORY_FALLBACK


# ── YAML I/O ─────────────────────────────────────────────────────────────

def _yaml_str(s):
    """Escape a string for a double-quoted YAML scalar."""
    if not s:
        return ""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def format_yaml_entry(entry):
    """Format a single repo entry as YAML lines."""
    lines = [f'  - name: "{_yaml_str(entry["name"])}"']
    lines.append(f'    url: {entry["url"]}')
    if entry.get("description"):
        lines.append(f'    description: "{_yaml_str(entry["description"])}"')
    lines.append(f'    category: {entry["category"]}')
    lines.append(f'    subcategory: {entry["subcategory"]}')
    lines.append(f'    stars: {entry["stars"]}')
    lines.append(f'    forks: {entry["forks"]}')
    if entry.get("language"):
        lines.append(f'    language: {entry["language"]}')
    if entry.get("topics"):
        lines.append(f'    topics:')
        for t in entry["topics"]:
            lines.append(f'      - {_yaml_str(t)}')
    if entry.get("pushed_at"):
        lines.append(f'    pushed_at: "{entry["pushed_at"]}"')
    if entry.get("created_at"):
        lines.append(f'    created_at: "{entry["created_at"]}"')
    if entry.get("open_issues"):
        lines.append(f'    open_issues: {entry["open_issues"]}')
    if entry.get("license") and entry["license"] not in ("NOASSERTION", ""):
        lines.append(f'    license: {entry["license"]}')
    return "\n".join(lines)


def load_existing_repos(path):
    """Load repos.yaml, return (names_set, entries_count)."""
    if not path.exists():
        return set(), 0
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    repos = data.get("repos", [])
    names = {r.get("name", "").lower().strip() for r in repos}
    return names, len(repos)


def append_repos(path, entries, topic_short="research"):
    """Append entries to repos.yaml, creating the file if needed."""
    lines = []
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        lines = content.rstrip("\n").split("\n")
        if lines == ["repos:"]:
            lines = ["repos:"]
        else:
            lines.append("")
    else:
        lines = [
            f"# Repositories relevant to {topic_short} research.",
            "# Generated by scripts/fetch/fetch_*_repos.py",
            f"# Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            "",
            "repos:",
        ]

    for entry in entries:
        lines.append(format_yaml_entry(entry))

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ── Entry normalisation ─────────────────────────────────────────────────

def normalize_entry(raw, category, subcategory_hint, cfg):
    """Convert a source-agnostic dict into a standard repos.yaml entry.

    ``raw`` must contain at least ``name`` and ``url``.  Recognised fields:
      name, url, description, stars, forks, language, topics (list of str),
      pushed_at, created_at, open_issues, license.

    Dates are truncated to YYYY-MM-DD if longer strings are provided.
    """
    subcat = subcategory_hint or classify_subcategory(
        raw.get("name", ""), raw.get("description", ""), raw.get("topics", []), cfg
    )
    return {
        "name": raw.get("name", ""),
        "url": raw.get("url", ""),
        "description": (raw.get("description") or "")[:200],
        "category": category or "method",
        "subcategory": subcat,
        "stars": int(raw.get("stars", 0) or 0),
        "forks": int(raw.get("forks", 0) or 0),
        "language": raw.get("language") or "",
        "topics": sorted(raw.get("topics") or []),
        "pushed_at": str(raw.get("pushed_at", ""))[:10],
        "created_at": str(raw.get("created_at", ""))[:10],
        "open_issues": int(raw.get("open_issues", 0) or 0),
        "license": raw.get("license") or "",
    }
