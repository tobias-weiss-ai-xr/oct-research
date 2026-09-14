"""Unit tests for scripts/generate_readme.py.

Verifies README generation logic on synthetic corpus data. Hermetic.
"""

from pathlib import Path

import pytest
import yaml

import research_config
import generate_readme as gen


@pytest.fixture
def sample_papers():
    """Small synthetic corpus for testing."""
    return [
        {
            "title": "Testing Framework Design",
            "date": "2026-01",
            "url": "https://arxiv.org/abs/2601.00001",
            "category": "testing",
            "subcategory": "frameworks",
            "authors": ["Alice Tester"],
            "abstract": "A framework for testing.",
            "venue": "arXiv",
        },
        {
            "title": "Property-Based Testing with Hypothesis",
            "date": "2025-12",
            "url": "https://arxiv.org/abs/2512.00002",
            "category": "testing",
            "subcategory": "methodology",
            "authors": ["Bob Tester"],
            "abstract": "Using property-based testing.",
            "venue": "arXiv",
        },
    ]


@pytest.fixture
def sample_cfg():
    """Minimal config for testing."""
    return {
        "topic": {"name": "Test Corpus", "short": "test"},
        "taxonomy": {
            "categories": [
                {"id": "testing", "display": "Testing"},
            ],
            "subcategories": [
                {"id": "frameworks", "display": "Frameworks"},
                {"id": "methodology", "display": "Methodology"},
            ],
        },
    }


def test_generate_json_creates_file(tmp_path, sample_papers):
    """Verify JSON generation writes valid file."""
    json_path = tmp_path / "papers.json"
    gen.generate_json(sample_papers, json_path)
    
    assert json_path.exists()
    import json
    data = json.loads(json_path.read_text())
    assert "papers" in data
    assert len(data["papers"]) == 2
    assert data["papers"][0]["title"] == "Testing Framework Design"


def test_generate_json_creates_parent_dirs(tmp_path, sample_papers):
    """Verify JSON generation creates missing parent directories."""
    json_path = tmp_path / "nested" / "dirs" / "papers.json"
    gen.generate_json(sample_papers, json_path)
    
    assert json_path.exists()


def test_generate_readme_replaces_section(tmp_path, sample_papers, sample_cfg):
    """Verify README paper-list section is replaced."""
    readme_path = tmp_path / "README.md"
    
    # Create a README with paper-list markers
    readme_text = f"""# Test Corpus

Some intro text.

{gen.readme_sections.PAPERLIST_START}
Old content that should be replaced.
{gen.readme_sections.PAPERLIST_END}

Some footer text.
"""
    readme_path.write_text(readme_text, encoding="utf-8")
    
    # Generate
    gen.generate_readme(sample_papers, readme_path, sample_cfg, check_mode=False)
    
    result = readme_path.read_text(encoding="utf-8")
    assert "Old content that should be replaced" not in result
    assert "Testing Framework Design" in result
    assert "Property-Based Testing with Hypothesis" in result


def test_generate_readme_no_section_skips_gracefully(tmp_path, sample_papers, sample_cfg):
    """Verify README with no paper-list section is not modified."""
    readme_path = tmp_path / "README.md"
    readme_text = "# Test Corpus\n\nNo paper list here.\n"
    readme_path.write_text(readme_text, encoding="utf-8")
    original = readme_text
    
    # This should NOT fail and should NOT modify the file
    gen.generate_readme(sample_papers, readme_path, sample_cfg, check_mode=False)
    
    result = readme_path.read_text(encoding="utf-8")
    assert result == original


def test_generate_readme_check_mode_updated(tmp_path, sample_papers, sample_cfg, capsys):
    """Verify check mode exits 1 when README is out of date."""
    readme_path = tmp_path / "README.md"
    readme_text = f"""# Test Corpus

{gen.readme_sections.PAPERLIST_START}
Old content.
{gen.readme_sections.PAPERLIST_END}
"""
    readme_path.write_text(readme_text, encoding="utf-8")
    
    with pytest.raises(SystemExit) as exc_info:
        gen.generate_readme(sample_papers, readme_path, sample_cfg, check_mode=True)
    
    assert exc_info.value.code == 1


def test_generate_readme_check_mode_current(tmp_path, sample_papers, sample_cfg, capsys):
    """Verify check mode exits 0 when README is current."""
    readme_path = tmp_path / "README.md"
    
    # First, generate the README to make it current
    readme_path.write_text("# Test Corpus\n\n", encoding="utf-8")
    gen.generate_readme(sample_papers, readme_path, sample_cfg, check_mode=False)
    
    # Now check should pass
    # But we need to capture sys.exit(0)
    try:
        gen.generate_readme(sample_papers, readme_path, sample_cfg, check_mode=True)
    except SystemExit as e:
        assert e.code == 0