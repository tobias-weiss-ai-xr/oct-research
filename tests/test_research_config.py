"""Unit tests for scripts/research_config.py shared config loader."""

import research_config as rc


def _cfg(**overrides):
    cfg = {
        "topic": {"name": "Test Topic", "short": "test-topic", "description": "desc",
                  "openalex_mailto": "cfg@example.com"},
        "taxonomy": {
            "categories": [{"id": "method", "display": "Methods"}],
            "subcategories": [{"id": "agentic", "display": "Agentic"}],
        },
        "arxiv_queries": ["cat:cs.AI"],
        "other_sources_queries": [],
        "openalex_queries": [],
        "trend_keywords": ["alpha", "beta"],
        "subcategory_keywords": [{"id": "method", "keywords": ["novel"]}],
    }
    cfg.update(overrides)
    return cfg


def test_get_categories_and_subcategories():
    cfg = _cfg()
    assert [c["id"] for c in rc.get_categories(cfg)] == ["method"]
    assert [s["id"] for s in rc.get_subcategories(cfg)] == ["agentic"]


def test_category_display_known():
    assert rc.category_display(_cfg(), "method") == "Methods"


def test_category_display_unknown_falls_back_to_id():
    assert rc.category_display(_cfg(), "nope") == "nope"


def test_subcategory_display_known():
    assert rc.subcategory_display(_cfg(), "agentic") == "Agentic"


def test_trend_keywords_from_config():
    assert rc.get_trend_keywords(_cfg()) == ["alpha", "beta"]


def test_trend_keywords_fallback_to_default_when_empty():
    assert rc.get_trend_keywords(_cfg(trend_keywords=[])) == rc._DEFAULT_TREND_KEYWORDS


def test_subcategory_keywords():
    kws = rc.get_subcategory_keywords(_cfg())
    assert ("method", ["novel"]) in kws


def test_display_name_uses_category_display():
    cfg = _cfg()  # category 'method' -> 'Methods'
    assert rc.display_name(cfg, "method") == "Methods"


def test_display_name_uses_subcategory_display():
    cfg = _cfg()  # subcategory 'agentic' -> 'Agentic'
    assert rc.display_name(cfg, "agentic") == "Agentic"


def test_display_name_fallback_title_case():
    cfg = _cfg()
    assert rc.display_name(cfg, "real-world") == "Real World"
    assert rc.display_name(cfg, "deep_learning") == "Deep Learning"


def test_openalex_mailto_from_config(monkeypatch):
    monkeypatch.delenv("OPENALEX_MAILTO", raising=False)
    assert rc.get_openalex_mailto(_cfg()) == "cfg@example.com"


def test_openalex_mailto_env_override(monkeypatch):
    monkeypatch.setenv("OPENALEX_MAILTO", "env@example.com")
    assert rc.get_openalex_mailto(_cfg()) == "env@example.com"


def test_openalex_mailto_final_fallback(monkeypatch):
    monkeypatch.delenv("OPENALEX_MAILTO", raising=False)
    assert "example" in rc.get_openalex_mailto(_cfg(topic={})) or \
        "@" in rc.get_openalex_mailto(_cfg(topic={}))


# ── validate_config ────────────────────────────────────────────────────────

def _valid_cfg():
    return {"topic": {"name": "X"},
            "taxonomy": {"categories": [{"id": "method"}],
                          "subcategories": [{"id": "core"}]}}


def test_validate_config_accepts_valid():
    assert rc.validate_config(_valid_cfg()) == []


def test_validate_config_duplicate_category():
    cfg = _valid_cfg()
    cfg["taxonomy"]["categories"] = [{"id": "a"}, {"id": "a"}]
    errs = rc.validate_config(cfg)
    assert any("duplicate id 'a'" in e for e in errs)


def test_validate_config_bad_id_case():
    cfg = _valid_cfg()
    cfg["taxonomy"]["categories"] = [{"id": "Method"}]
    errs = rc.validate_config(cfg)
    assert any("lowercase kebab-case" in e for e in errs)


def test_validate_config_missing_name():
    cfg = _valid_cfg()
    cfg["topic"] = {}
    errs = rc.validate_config(cfg)
    assert any("topic.name" in e for e in errs)


def test_validate_config_empty_categories():
    cfg = _valid_cfg()
    cfg["taxonomy"]["categories"] = []
    errs = rc.validate_config(cfg)
    assert any("non-empty list" in e for e in errs)


def test_validate_config_ghost_subcategory_keyword():
    cfg = _valid_cfg()
    cfg["subcategory_keywords"] = [{"id": "ghost", "keywords": ["x"]}]
    errs = rc.validate_config(cfg)
    assert any("does not match any subcategory" in e for e in errs)


def test_validate_config_non_mapping():
    assert rc.validate_config("hello") != []
    assert rc.validate_config(None) != []
