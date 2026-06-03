"""Tests for export_format helper functions — italic stripping, HTML wrapping."""

from __future__ import annotations

from app.services.export_format import markdown_to_html_fragment, rendered_to_plain_text, wrap_html_document


def test_plain_text_strips_italics():
    """Single-star italic markers are removed."""
    result = rendered_to_plain_text("This is *italic* text with *more italic*")
    assert "*" not in result
    assert "italic" in result
    assert "more italic" in result


def test_plain_text_strips_bold():
    result = rendered_to_plain_text("This is **bold** text")
    assert "**" not in result
    assert "bold" in result


def test_plain_text_strips_links():
    result = rendered_to_plain_text("Click [here](https://example.com) now")
    assert "here" in result
    assert "https://example.com" not in result
    assert "[" not in result


def test_plain_text_strips_headings():
    result = rendered_to_plain_text("# Heading\n## Sub\nBody text")
    assert "#" not in result
    assert "Heading" in result
    assert "Sub" in result


def test_plain_text_collapses_blank_lines():
    result = rendered_to_plain_text("A\n\n\n\nB")
    assert "\n\n\n" not in result
    assert "A" in result
    assert "B" in result


def test_plain_text_strips_backticks():
    result = rendered_to_plain_text("Use `code` here")
    assert "`" not in result
    assert "code" in result


def test_html_fragment():
    result = markdown_to_html_fragment("# Hello\n\nWorld")
    assert "<h1>" in result
    assert "Hello" in result


def test_wrap_html_document():
    result = wrap_html_document("<p>content</p>")
    assert "<!DOCTYPE html>" in result
    assert "<p>content</p>" in result
    assert 'charset="utf-8"' in result
