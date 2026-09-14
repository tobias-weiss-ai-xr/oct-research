"""Tests for github_queries loading in fetch_github_repos.py."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "fetch"))

from fetch_github_repos import load_github_queries


@pytest.fixture
def cfg():
    return {"github_queries": [
        {"query": "dicom language:Rust", "category": "method"},
        {"query": "oct language:Rust", "min_stars": 100},
        {"query": ""},
    ]}


def test_drops_empty_query(cfg):
    assert len(load_github_queries(cfg)) == 2


def test_min_stars_only_when_explicit(cfg):
    queries = load_github_queries(cfg)
    assert "min_stars" not in queries[0]
    assert queries[1]["min_stars"] == 100


def test_no_queries(cfg_empty=None):
    assert load_github_queries({}) == []


def test_encode_gh_query():
    from fetch_github_repos import encode_gh_query
    assert encode_gh_query('dicom language:Rust') == 'dicom+language:Rust'
    assert encode_gh_query('stars:>5') == 'stars:%3E5'
    assert encode_gh_query('"optical coherence tomography"') == \
        '%22optical+coherence+tomography%22'
    # existing + separators are left untouched
    assert encode_gh_query('ddiom language:Rust+stars:>5') == \
        'ddiom+language:Rust+stars:%3E5'
