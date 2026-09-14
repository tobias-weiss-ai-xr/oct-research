"""Unit tests for scripts/fetch/fetch_metadata.py helpers."""

from fetch_metadata import extract_arxiv_id


def test_extract_arxiv_id_abs_url():
    assert extract_arxiv_id("https://arxiv.org/abs/1234.56789") == "1234.56789"


def test_extract_arxiv_id_with_version():
    assert extract_arxiv_id("https://arxiv.org/abs/1234.56789v2") == "1234.56789"


def test_extract_arxiv_id_pdf_url():
    assert extract_arxiv_id("https://arxiv.org/pdf/9876.54321") == "9876.54321"


def test_extract_arxiv_id_no_match():
    assert extract_arxiv_id("https://example.com/paper") is None
    assert extract_arxiv_id("") is None
