"""Unit tests for scripts/validate_papers.py pure functions + validation logic."""

import sys
from unittest import mock

import pytest

import research_config
import validate_papers as vp


# ── normalize_arxiv_url ──────────────────────────────────────────────────

def test_normalize_arxiv_url_abs():
    url = "https://arxiv.org/abs/1234.56789"
    assert vp.normalize_arxiv_url(url) == url


def test_normalize_arxiv_url_strips_pdf():
    assert vp.normalize_arxiv_url("https://arxiv.org/pdf/1234.56789") == \
        "https://arxiv.org/abs/1234.56789"


def test_normalize_arxiv_url_strips_version():
    assert vp.normalize_arxiv_url("https://arxiv.org/abs/1234.56789v3") == \
        "https://arxiv.org/abs/1234.56789"


def test_normalize_arxiv_url_doi_redirect():
    assert vp.normalize_arxiv_url("https://doi.org/10.48550/arXiv.1234.56789") == \
        "https://arxiv.org/abs/1234.56789"


def test_normalize_arxiv_url_www():
    assert vp.normalize_arxiv_url("https://www.arxiv.org/abs/1234.56789") == \
        "https://arxiv.org/abs/1234.56789"


def test_normalize_arxiv_url_non_arxiv_unchanged():
    url = "https://example.com/paper"
    assert vp.normalize_arxiv_url(url) == url


def test_normalize_arxiv_url_oldstyle_strips_version():
    assert vp.normalize_arxiv_url("https://arxiv.org/abs/math/0311487v1") == \
        "https://arxiv.org/abs/math/0311487"


def test_normalize_arxiv_url_oldstyle_abs():
    assert vp.normalize_arxiv_url("https://arxiv.org/abs/hep-th/9901001") == \
        "https://arxiv.org/abs/hep-th/9901001"


def test_arxiv_url_pattern_accepts_oldstyle():
    assert vp.ARXIV_URL_PATTERN.match("https://arxiv.org/abs/math/0311487")
    assert vp.ARXIV_URL_PATTERN.match("https://arxiv.org/abs/1234.56789")
    assert not vp.ARXIV_URL_PATTERN.match("https://arxiv.org/abs/math/0311487v1")


# ── clean_latex_artifacts ────────────────────────────────────────────────

def test_clean_latex_inline_math():
    assert vp.clean_latex_artifacts("We study $x^2$ results") == "We study x^2 results"


def test_clean_latex_textit():
    assert vp.clean_latex_artifacts(r"\textit{emphasized} text") == "emphasized text"


def test_clean_latex_display_math():
    assert vp.clean_latex_artifacts(r"\[E = mc^2\] done") == "E = mc^2 done"


def test_clean_latex_requires():
    assert vp.clean_latex_artifacts(r"$\mathbf{W}$ weights") == "W weights"


def test_clean_latex_empty_returns_empty():
    assert vp.clean_latex_artifacts("") == ""
    assert vp.clean_latex_artifacts(None) is None


def test_clean_latex_collapses_whitespace():
    assert vp.clean_latex_artifacts("a   b\n\n  c") == "a b c"


# ── LATEX_PATTERNS detect artifacts ─────────────────────────────────────

def test_latex_patterns_detect_math():
    assert any(p.search("cost is $O(n^2)$") for p in vp.LATEX_PATTERNS)


def test_latex_patterns_detect_textbf():
    assert any(p.search(r"\textbf{Important}") for p in vp.LATEX_PATTERNS)


def test_latex_patterns_clean_text_ok():
    assert not any(p.search("A normal title with numbers 42 and 2026") for p in vp.LATEX_PATTERNS)


# ── date / URL validation helpers ────────────────────────────────────────

def test_date_pattern_valid():
    assert vp.DATE_PATTERN.match("2026-03")
    assert vp.DATE_PATTERN.match("2024-12")


def test_date_pattern_invalid():
    assert not vp.DATE_PATTERN.match("2026-13")
    assert not vp.DATE_PATTERN.match("2026-3")
    assert not vp.DATE_PATTERN.match("2026")


def test_url_pattern_requires_https():
    assert vp.URL_PATTERN.match("https://example.com")
    assert not vp.URL_PATTERN.match("http://example.com")


def test_vanity_domains_flagged():
    assert vp.VANITY_DOMAINS.search("https://zenodo.org/doi/10.5281/zenodo.123")
    assert vp.VANITY_DOMAINS.search("https://www.researchsquare.com/article/xyz")
    assert not vp.VANITY_DOMAINS.search("https://arxiv.org/abs/1234.56789")


# ── validate_papers end-to-end ──────────────────────────────────────────

@pytest.fixture
def cfg():
    return {
        "taxonomy": {
            "categories": [{"id": "method", "display": "Methods"},
                           {"id": "survey", "display": "Surveys"}],
            "subcategories": [{"id": "agentic", "display": "Agentic"},
                              {"id": "hybrid", "display": "Hybrid"}],
        }
    }


def _paper(**overrides):
    p = {
        "title": "A paper",
        "date": "2025-01",
        "url": "https://arxiv.org/abs/2501.00001",
        "category": "method",
        "subcategory": "agentic",
        "authors": ["A"],
        "abstract": "",
        "venue": "",
    }
    p.update(overrides)
    return p


def test_validate_ok(cfg):
    data = {"papers": [_paper()]}
    errors, warnings, fixed, _ = vp.validate_papers(data, cfg)
    assert errors == []
    assert warnings == []
    assert fixed == 0


def test_validate_missing_required(cfg):
    data = {"papers": [_paper(subcategory="", url="")]}
    errors, _, _, _ = vp.validate_papers(data, cfg)
    assert any("missing required field 'subcategory'" in e for e in errors)
    assert any("missing required field 'url'" in e for e in errors)


def test_validate_invalid_category(cfg):
    data = {"papers": [_paper(category="bogus")]}
    errors, _, _, _ = vp.validate_papers(data, cfg)
    assert any("invalid category 'bogus'" in e for e in errors)


def test_validate_invalid_subcategory(cfg):
    data = {"papers": [_paper(subcategory="nope")]}
    errors, _, _, _ = vp.validate_papers(data, cfg)
    assert any("invalid subcategory 'nope'" in e for e in errors)


def test_validate_duplicate(cfg):
    data = {"papers": [_paper(), _paper()]}
    errors, _, _, _ = vp.validate_papers(data, cfg)
    assert any("duplicate entry" in e for e in errors)


def test_validate_future_date(cfg):
    from datetime import datetime
    fixed = datetime(2025, 1, 1)
    with mock.patch.object(vp, "TODAY", fixed):
        data = {"papers": [_paper(date="2026-03")]}
        errors, _, _, _ = vp.validate_papers(data, cfg)
    assert any("future date '2026-03'" in e for e in errors)


def test_validate_past_date_ok(cfg):
    from datetime import datetime
    fixed = datetime(2025, 1, 1)
    with mock.patch.object(vp, "TODAY", fixed):
        data = {"papers": [_paper(date="2024-12")]}
        errors, _, _, _ = vp.validate_papers(data, cfg)
    assert errors == []


def test_validate_fix_normalizes_arxiv_url(cfg):
    data = {"papers": [_paper(url="https://arxiv.org/pdf/2501.00001")]}
    errors, _, fixed, _ = vp.validate_papers(data, cfg, fix=True)
    assert errors == []
    assert data["papers"][0]["url"] == "https://arxiv.org/abs/2501.00001"


def test_no_papers_is_error(cfg):
    data = {"papers": []}
    errors, _, _, _ = vp.validate_papers(data, cfg)
    assert any("no papers" in e for e in errors)
