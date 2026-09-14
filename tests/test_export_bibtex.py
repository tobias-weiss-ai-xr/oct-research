"""Unit tests for scripts/export_bibtex.py sanitization + key generation."""

from export_bibtex import sanitize_bibtex


def test_sanitize_bibtex_escapes_special_chars():
    assert sanitize_bibtex("A & B") == r"A \& B"
    assert sanitize_bibtex("100%") == r"100\%"
    assert sanitize_bibtex("C#") == r"C\#"


def test_sanitize_bibtex_escapes_braces_and_underscore():
    assert sanitize_bibtex("x_y") == r"x\_y"
    assert sanitize_bibtex("{brace}") == r"\{brace\}"


def test_sanitize_bibtex_plain_text_unchanged():
    assert sanitize_bibtex("Plain text") == "Plain text"
    assert sanitize_bibtex("") == ""
