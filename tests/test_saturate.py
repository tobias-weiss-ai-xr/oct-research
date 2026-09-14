"""Unit tests for pure helpers in scripts/fetch/saturate_papers.py."""

import re

import saturate_papers as sp


def test_title_similarity_identical():
    assert sp.title_similarity("Alpha Method", "Alpha Method") == 1.0


def test_title_similarity_close():
    assert sp.title_similarity("A Novel Agent Framework", "a novel agent framework") > 0.9


def test_title_similarity_different():
    assert sp.title_similarity("Unrelated Topic", "Completely Different") < 0.5


def test_dedup_title_matches_similar():
    existing = ["the quick brown agent"]
    assert sp.dedup_title("The quick brown agent", existing) is True


def test_dedup_title_no_match():
    existing = ["the quick brown agent"]
    assert sp.dedup_title("a totally different paper title", existing) is False


def test_is_relevant_no_keywords_accepts_all():
    assert sp.is_relevant("anything", "anything", []) is True
    assert sp.is_relevant("", "", []) is True


def test_is_relevant_matches_keyword_in_abstract():
    assert sp.is_relevant("Some title", "This concerns manipulation details",
                          ["manipulation"]) is True


def test_is_relevant_rejects_when_no_match():
    assert sp.is_relevant("Some title", "unrelated abstract", ["manipulation"]) is False


def test_get_queries_expands_across_cats():
    cfg = {
        "arxiv_queries": ["abs:\"my topic\""],
        "arxiv_expand_cats": ["cs.AI", "cs.LG"],
        "topic": {"short": "topic"},
    }
    queries = sp.get_queries(cfg)
    # expands 1 base query across 2 categories
    assert len(queries) == 2
    assert all(q["query"].startswith("cat:") for q in queries)


def test_get_queries_preserves_explicit_cat():
    cfg = {
        "arxiv_queries": [{"query": 'cat:cs.CL AND abs:"agents"'}],
        "arxiv_expand_cats": ["cs.AI", "cs.CL"],
        "topic": {"short": "topic"},
    }
    queries = sp.get_queries(cfg)
    # original kept + expanded into cs.AI (only the diff cat)
    cats = [re.search(r"cat:(\S+)", q["query"]).group(1) for q in queries]
    assert "cs.CL" in cats and "cs.AI" in cats

