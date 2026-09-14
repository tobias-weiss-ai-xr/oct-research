"""Unit tests for scripts/fetch/fetch_new_papers.py classification helpers."""

from fetch_new_papers import classify_subcategory
import research_config


def _cfg_with_subcategory_keywords():
    return {
        "taxonomy": {
            "subcategories": [
                {"id": "theory", "category": "math"},
                {"id": "method", "category": "cs"},
                {"id": "survey"},
            ]
        },
        "subcategory_keywords": [
            {"id": "theory", "keywords": ["formal", "proof"]},
            {"id": "method", "keywords": ["novel approach", "framework"]},
            {"id": "survey", "keywords": ["survey", "overview"]},
        ],
    }


def test_classify_uses_config_keyword():
    cfg = _cfg_with_subcategory_keywords()
    assert classify_subcategory("A Survey of the Field", "", cfg) == "survey"


def test_classify_config_rule_wins_over_heuristic():
    cfg = _cfg_with_subcategory_keywords()
    # 'overview' should map to survey via config even though heuristic would
    # also catch 'survey'
    assert classify_subcategory("An overview of methods", "", cfg) == "survey"


def test_classify_heuristic_fallback():
    cfg = _cfg_with_subcategory_keywords()
    # 'formal proof' matches heuristic 'theory' (also a config keyword)
    assert classify_subcategory("Formal Proof of Convergence", "", cfg) == "theory"


def test_classify_last_resort_first_subcategory():
    cfg = _cfg_with_subcategory_keywords()
    assert classify_subcategory("Totally neutral title", "equally neutral abstract", cfg) == "theory"


def test_classify_category_scoped_keywords():
    cfg = _cfg_with_subcategory_keywords()
    # 'formal proof' keyword belongs to theory (category math); a cs paper must
    # never fall back to theory just because its text mentions a shared keyword.
    assert classify_subcategory(
        "A novel approach with a formal proof appendix", "", cfg, category="cs"
    ) == "method"


def test_classify_category_scoped_fallback_default():
    cfg = _cfg_with_subcategory_keywords()
    # No keywords match inside the cs category -> default to its first subcategory.
    assert classify_subcategory("Totally neutral cs title", "neutral cs abstract", cfg, category="cs") == "method"


def test_classify_never_returns_labels_missing_from_taxonomy():
    cfg = _cfg_with_subcategory_keywords()
    # 'application'/'evaluation' are heuristic labels NOT declared in cfg;
    # the classifier must not emit them even when text matches.
    result = classify_subcategory("An application survey in production", "benchmark evaluation", cfg)
    assert result in {"theory", "method", "survey"}
