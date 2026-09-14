"""Unit tests for the digest anti-saturation helpers in run_pipeline.py.

Covers:
  * select_with_quota — caps each source's share of the digest slots.
  * _within_recent    — date-window filtering (keeps undated items).
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import run_pipeline as rp  # noqa: E402


def _item(source, score, digest=None, published=""):
    return {
        "source": source,
        "score": score,
        "digest": digest or f"{source}-{score}",
        "published": published,
    }


def test_select_with_quota_caps_dominant_source():
    # Three sources with enough competing high-score items to force the cap.
    # top=6, share 0.4 -> quota 2. Source A has the 4 highest scores but must
    # be capped at 2; the rest of the digest is filled by B and C.
    items = [
        _item("A", 10), _item("A", 9), _item("A", 8), _item("A", 7),
        _item("B", 6), _item("B", 5), _item("B", 4), _item("B", 3),
        _item("C", 2), _item("C", 1),
    ]
    out = rp.select_with_quota(items, 6, 0.4)
    assert len(out) == 6
    from collections import Counter
    counts = Counter(i["source"] for i in out)
    assert counts["A"] == 2            # hard-capped at quota
    assert counts["B"] == 2
    assert counts["C"] == 2
    # A's two slots are its highest scores
    a_scores = sorted(i["score"] for i in out if i["source"] == "A")
    assert a_scores == [9, 10]


def test_select_with_quota_no_cap_needed():
    items = [_item("A", 3), _item("B", 2), _item("C", 1)]
    out = rp.select_with_quota(items, 3, 0.4)
    assert [i["source"] for i in out] == ["A", "B", "C"]


def test_select_with_quota_respects_top_n():
    items = [_item(f"S{i}", 5 - i * 0.1) for i in range(10)]
    out = rp.select_with_quota(items, 4, 0.4)
    assert len(out) == 4


def test_select_with_quota_empty():
    assert rp.select_with_quota([], 10, 0.4) == []


def test_within_recent_keeps_undated():
    # Items we cannot date must never be dropped.
    assert rp._within_recent("", None) is True
    assert rp._within_recent("not-a-date", None) is True


def test_within_recent_filters_old():
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    recent = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cutoff = now - timedelta(days=14)
    assert rp._within_recent(old, cutoff) is False
    assert rp._within_recent(recent, cutoff) is True
