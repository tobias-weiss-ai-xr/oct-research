"""Fetch + normalize news / intelligence sources.

Every adapter returns a list of normalized item dicts:

    {
        "digest":      sha1(id-string),        # stable dedup key
        "source":      <source name>,
        "source_label":<human label>,
        "category":    paper|discussion|changelog,
        "title":       str,
        "url":         str,
        "summary":     str,
        "authors":     [str],
        "published":   ISO8601 str or "",
        "extra":       {},
    }
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.parse
import urllib.request

import calendar
from datetime import datetime, timezone


import feedparser

_CLEAN_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _norm(text: str | None, limit: int = 500) -> str:
    """Strip HTML, unescape entities, collapse whitespace, truncate."""
    if not text:
        return ""
    txt = _CLEAN_RE.sub(" ", text)
    txt = html.unescape(txt)
    txt = _WS_RE.sub(" ", txt).strip()
    return txt[:limit]


def _dt_from_struct(st):
    """Convert a feedparser time.struct_time (UTC) to a tz-aware datetime."""
    return datetime.fromtimestamp(calendar.timegm(st), tz=timezone.utc)


def _iso(dt):
    try:
        if hasattr(dt, "tm_year"):          # feedparser struct_time (UTC)
            return _dt_from_struct(dt).strftime("%Y-%m-%dT%H:%M:%SZ")
        if hasattr(dt, "year"):
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        pass
    return None


def _item(**kw) -> dict:
    id_src = f"{kw.get('title','')}|{kw.get('url','')}|{kw.get('source','')}"
    kw["digest"] = hashlib.sha1(id_src.encode("utf-8")).hexdigest()[:16]
    # normalize display label
    if "source_label" not in kw:
        kw["source_label"] = kw.get("label") or kw.get("source", "")
    kw.setdefault("extra", {})
    return kw


class Fetcher:
    def __init__(self, timeout: int = 20):
        self.timeout = timeout

    # ------------------------------------------------------ generic RSS/Atom
    def fetch_rss(self, url: str, *, source: str, category: str,
                  weight: float, label: str | None = None, agent: str | None = None) -> list[dict]:
        ua = agent or ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
        parsed = feedparser.parse(url, agent=ua)
        out = self._rss_entries(parsed, source, category, weight, label)
        if not out:
            # Reddit / some CDNs return empty on first hit; retry once
            import time
            time.sleep(2)
            parsed = feedparser.parse(url, agent=ua)
            out = self._rss_entries(parsed, source, category, weight, label)
        if not out:
            print(f"    (empty: status={getattr(parsed, 'status', None)} "
                  f"bozo={parsed.get('bozo', 0)}) ", flush=True)
        return out

    def _rss_entries(self, parsed, source, category, weight, label):
        out = []
        for e in parsed.entries:
            title = (e.get("title") or "").strip()
            link = e.get("link") or e.get("id") or ""
            if not title or not link:
                continue
            summary = _norm(e.get("summary") or e.get("description") or "")
            # strip feed boilerplate breadcrumbs / metadata blocks
            if summary in ("Comments", "Comment", "No comments"):
                summary = ""
            if "Article URL:" in summary:
                summary = summary.split("Article URL:")[0].strip()
            authors = [a.get("name") for a in e.get("authors", []) if a.get("name")]
            # feedparser exposes parsed dates as a UTC struct_time.
            published = ""
            pp = e.get("published_parsed") or e.get("updated_parsed")
            if pp:
                try:
                    published = _dt_from_struct(pp).strftime("%Y-%m-%dT%H:%M:%SZ")
                except (TypeError, ValueError, OverflowError):
                    published = ""
            out.append(_item(
                source=source, label=label or source, category=category,
                weight=weight, title=title, url=link, summary=summary,
                authors=authors, published=published,
            ))
        return out

    # ---------------------------------------------------------- arXiv API
    def fetch_arxiv(self, categories, *, source: str, max_r: int,
                    weight: float, query: str | None = None) -> list[dict]:
        cat_part = " OR ".join(f"cat:{c}" for c in categories)
        # Optional free-text query AND-ed with the category filter — lets a
        # source pull only papers that explicitly mention its focus (e.g.
        # AIOps), instead of every paper in a broad category.
        q = f"({query}) AND ({cat_part})" if query else cat_part
        url = ("https://export.arxiv.org/api/query?" + urllib.parse.urlencode({
            "search_query": q, "start": 0, "max_results": max_r,
            "sortBy": "submittedDate", "sortOrder": "descending",
        }))
        return self._parse_arxiv(feedparser.parse(url), source, weight)

    def _parse_arxiv(self, parsed, source, weight) -> list[dict]:
        out = []
        for e in parsed.entries:
            title = _norm(e.get("title", "")).strip()
            link = (e.get("id") or "").strip()
            if not title or not link:
                continue
            authors = [a.get("name") for a in e.get("authors", []) if a.get("name")]
            summary = _norm(e.get("summary", ""))
            abs_url = link.replace("http://", "https://").replace("/pdf/", "/abs/")
            cats = ", ".join(t.get("term", "") for t in e.get("tags", []) if t.get("term"))
            out.append(_item(
                source=source, label=source, category="paper", weight=weight,
                title=title, url=abs_url, summary=summary, authors=authors,
                published=_iso(e.get("published_parsed")),
                extra={"categories": cats},
            ))
        return out

    # ------------------------------------------- CISA KEV catalog (JSON)
    def fetch_cisa_kev(self, url: str, *, source: str, category: str,
                       weight: float) -> list[dict]:
        """Fetch CISA Known Exploited Vulnerabilities (JSON).

        Each vulnerability is a single actionable item: exploited in the
        wild against known software.  Normalised to the item schema with
        exploit metadata in ``extra``.
        """
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "devsecops-digest"})
            data = json.loads(urllib.request.urlopen(req, timeout=self.timeout).read())
        except Exception as exc:  # noqa: BLE001
            print(f"    (empty: {exc})")
            return []

        vulns = data.get("vulnerabilities", [])
        out = []
        for v in vulns:
            cve = v.get("cveID", "")
            if not cve:
                continue
            title = f"[KEV] {cve}: {v.get('vulnerabilityName', '')}"
            summary = _norm(v.get("shortDescription", "")) or \
                f"Actively exploited vulnerability in {v.get('vendorProject', '')} " \
                f"{v.get('product', '')}."
            out.append(_item(
                source=source, label="CISA KEV", category=category,
                weight=weight, title=title,
                url=f"https://nvd.nist.gov/vuln/detail/{cve}",
                summary=summary,
                published=v.get("dateAdded", ""),
                extra={
                    "cve": cve,
                    "vendor": v.get("vendorProject", ""),
                    "product": v.get("product", ""),
                    "required_action": v.get("requiredAction", ""),
                    "due_date": v.get("dueDate", ""),
                    "known_ransomware": v.get("knownRansomwareCampaignUse", ""),
                },
            ))
        return out

    # -------------------------------------------------- GitHub releases
    def fetch_github_releases(self, repos, *, source, weight) -> list[dict]:
        out = []
        for repo in repos:
            api = f"https://api.github.com/repos/{repo}/releases?per_page=8"
            try:
                req = urllib.request.Request(
                    api, headers={"Accept": "application/vnd.github+json",
                                  "User-Agent": "devsecops-digest"})
                data = json.loads(urllib.request.urlopen(req, timeout=self.timeout).read())
            except Exception as exc:  # noqa: BLE001
                print(f"  [warn] GitHub releases {repo}: {exc}")
                continue
            for r in data or []:
                title = f"[{repo}] {r.get('name') or r.get('tag_name', '')}"
                out.append(_item(
                    source=source, label=f"github:{repo}", category="changelog",
                    weight=weight, title=title, url=r.get("html_url") or api,
                    summary=_norm(r.get("body") or "") or (r.get("tag_name") or ""),
                    published=r.get("published_at"),
                    extra={"tag": r.get("tag_name")},
                ))
        return out