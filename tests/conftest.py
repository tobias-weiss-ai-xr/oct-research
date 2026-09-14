"""Shared pytest fixtures / path setup for the *-research corpus test suite.

Ensures that ``scripts/`` and ``tools/`` are importable when running tests
from the repository root, mirroring how the pipeline scripts import
``research_config`` and each other.

Provides common fixtures for corpus-agnostic testing:
- mini_cfg: minimal taxonomy config for synthetic-data tests
- mini_papers: small list of valid papers for basic validation tests
"""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

for _p in ("scripts", "scripts/fetch", "tools"):
    _path = str(REPO / _p)
    if _path not in sys.path:
        sys.path.insert(0, _path)


@pytest.fixture
def mini_cfg():
    """A minimal taxonomy config for synthetic-data tests."""
    return {
        "topic": {"name": "Test Corpus", "short": "test"},
        "taxonomy": {
            "categories": [
                {"id": "test-cat", "display": "Test Category"},
            ],
            "subcategories": [
                {"id": "test-sub", "display": "Test Subcategory"},
            ],
        },
    }


@pytest.fixture
def mini_papers():
    """A small list of valid papers spanning minimal categories."""
    return [
        {
            "title": "Test Paper One",
            "date": "2026-01",
            "url": "https://arxiv.org/abs/2405.12345",
            "category": "test-cat",
            "subcategory": "test-sub",
            "authors": ["Ada Lovelace"],
            "abstract": "A study of software craft.",
            "venue": "arXiv",
        },
        {
            "title": "Test Paper Two",
            "date": "2025-06",
            "url": "https://doi.org/10.1000/xyz123",
            "category": "test-cat",
            "subcategory": "test-sub",
            "authors": ["Grace Hopper"],
            "abstract": "Survey of practices.",
            "venue": "Journal of Testing",
        },
    ]
