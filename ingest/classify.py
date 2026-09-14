"""Keyword-based topic classification + relevance scoring.

Relevance = baseline + source-weight share + topic-match bonuses + recency.
Security / policy-code topics are weighted more heavily than generic ones.
"""

from __future__ import annotations

import re
import time
from datetime import datetime


def _txt(item: dict) -> str:
    return f"{item.get('title', '')} {item.get('summary', '')} {item.get('source_label', '')}".lower()


class Classifier:
    def __init__(self, keywords: dict, *, fresh_window_days: int = 3, baseline: float = 0.2):
        self.topics: dict[str, list[re.Pattern]] = {}
        for topic, words in (keywords or {}).items():
            pats = []
            for w in words:
                try:
                    pats.append(re.compile(rf"(?<!\w){re.escape(w)}(?!\w)"))
                except re.error:
                    continue
            if pats:
                self.topics[topic] = pats
        self.fresh_window_days = fresh_window_days
        self.baseline = baseline

    def tags(self, item: dict) -> list[str]:
        text = _txt(item)
        return [t for t, pats in self.topics.items() if any(p.search(text) for p in pats)]

    def score(self, item: dict, *, source_weight: float = 1.0) -> float:
        text = _txt(item)
        s = self.baseline + source_weight * 0.4
        for topic, pats in self.topics.items():
            count = sum(len(p.findall(text)) for p in pats)
            if not count:
                continue
            boost = 0.9 if topic in ("security", "policycode", "aiops") else 0.5
            s += boost * min(count, 3)
        pub = item.get("published") or ""
        if pub:
            dt = _parse(pub)
            if dt is not None:
                age = time.time() - dt
                if 0 <= age < self.fresh_window_days * 86400:
                    s += 0.4
        return round(s, 3)


def _parse(pub: str):
    try:
        dt = datetime.fromisoformat(pub.replace("Z", "+00:00")).timestamp()
    except ValueError:
        try:
            dt = datetime.fromtimestamp(float(pub)).timestamp()
        except (ValueError, TypeError):
            return None
    return dt