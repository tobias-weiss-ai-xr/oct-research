"""Unit tests for scripts/fetch/repos_common.py shared helpers."""

import pytest

from repos_common import (
    _norm,
    _tokenize,
    _word_re,
    is_relevant_repo,
    classify_subcategory,
    normalize_entry,
    load_topic_signals,
    _yaml_str,
)


# ── text helpers ─────────────────────────────────────────────────────────

def test_norm_lowercases_and_collapses():
    assert _norm("Foo-Bar / Baz") == "foo bar baz"


def test_tokenize_splits():
    assert _tokenize("model context protocol") == ["model", "context", "protocol"]
    assert _tokenize("foo-bar") == ["foo", "bar"]


def test_word_re_single_token():
    re_ = _word_re(["security"])
    assert re_.search("AI security paper")
    assert not re_.search("insecure model")


def test_word_re_multi_token():
    re_ = _word_re(["supply chain"])
    assert re_.search("about supply chains")
    assert not re_.search("supply and demand")


# ── relevance filtering ─────────────────────────────────────────────────

def test_is_relevant_repo_empty_pattern_passes():
    assert is_relevant_repo("anything", "desc", [], None) is True


def test_is_relevant_repo_matches():
    re_ = _word_re(["security"])
    assert is_relevant_repo("my-security-tool", "", [], re_)
    assert not is_relevant_repo("unrelated-name", "pizza recipe", [], re_)


def test_load_topic_signals_skips_stopwords():
    cfg = {"topic": {"name": "LLM Security Research", "short": "llm-security",
                     "description": "security for language models"},
           "taxonomy": {"categories": [{"id": "method"}], "subcategories": [{"id": "core"}]}}
    sigs = load_topic_signals(cfg)
    assert "research" not in sigs  # stopword filtered
    assert "security" in sigs
    assert "method" not in sigs  # 'method' is itself a stopword


# ── subcategory classification ──────────────────────────────────────────

def test_classify_subcategory_from_taxonomy_id():
    cfg = {"taxonomy": {"subcategories": [{"id": "theory"}, {"id": "application"}]}}
    assert classify_subcategory("a framework spec", "", [], cfg) == "theory"


def test_classify_subcategory_heuristic_tool():
    cfg = {"taxonomy": {"subcategories": [{"id": "theory"}, {"id": "eval"}]}}
    assert classify_subcategory("cli scanner tool", "", [], cfg) == "application"


def test_classify_subcategory_fallback():
    cfg = {"taxonomy": {"subcategories": []}}
    assert classify_subcategory("totally neutral thing", "", [], cfg) == "application"


# ── normalize_entry ─────────────────────────────────────────────────────

def test_normalize_entry_basic():
    cfg = {"taxonomy": {"subcategories": [{"id": "method"}]}}
    entry = normalize_entry(
        {"name": "org/repo", "url": "https://github.com/org/repo",
         "stars": "150", "forks": "20", "pushed_at": "2026-01-15T00:00:00Z"},
        "application", "", cfg,
    )
    assert entry["name"] == "org/repo"
    assert entry["stars"] == 150
    assert entry["forks"] == 20
    assert entry["category"] == "application"
    assert entry["pushed_at"] == "2026-01-15"  # date truncated


def test_normalize_entry_date_truncation():
    cfg = {"taxonomy": {"subcategories": [{"id": "x"}]}}
    entry = normalize_entry(
        {"name": "a/b", "url": "https://x", "created_at": "2025-06-01T10:00:00+00:00"},
        "", "", cfg,
    )
    assert entry["created_at"] == "2025-06-01"


# ── yaml escaping ───────────────────────────────────────────────────────

def test_yaml_str_escapes_quotes_and_backslashes():
    assert _yaml_str('say "hi"') == 'say \\"hi\\"'
    assert _yaml_str("a\\b") == "a\\\\b"
    assert _yaml_str("") == ""
