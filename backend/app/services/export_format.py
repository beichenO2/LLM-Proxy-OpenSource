"""HTML and plain-text formatting for exported rendered Markdown (D-49–D-51).

TXT output is best-effort stripping of common Markdown markers; it is not a full
Markdown-to-plaintext parser. Helpers must not log secret or identity values.
"""

from __future__ import annotations

import re

from markdown_it import MarkdownIt

_md = MarkdownIt().enable("table")


def markdown_to_html_fragment(md: str) -> str:
    """Convert Markdown string to an HTML fragment (no document wrapper)."""
    return _md.render(md)


def wrap_html_document(body_inner: str) -> str:
    """Wrap inner HTML in a minimal HTML5 document with charset and basic typography."""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>"
        '<meta charset="utf-8">'
        "<title>export</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:48rem;margin:2rem auto;line-height:1.5}</style>"
        "</head>\n"
        f"<body>{body_inner}</body>\n"
        "</html>\n"
    )


def rendered_to_plain_text(rendered_md: str) -> str:
    """
    Strip common Markdown markers from rendered text (best-effort per D-51).

    Applies: markdown link → link text only, backticks removed, ``**`` removed,
    repeated ``*`` around tokens removed, ATX ``#`` line prefixes removed,
    collapsed blank lines. Does not log content.
    """
    s = rendered_md
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = s.replace("`", "")
    s = s.replace("**", "")
    # italic *word* (not **)
    for _ in range(8):
        next_s = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"\1", s)
        if next_s == s:
            break
        s = next_s
    s = re.sub(r"^#+\s*", "", s, flags=re.MULTILINE)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()
