"""Markdown cleaning helpers: whitespace, control-char, and heading
normalization applied to converter output before it is written to disk.

Pure text transforms — no I/O, no external libs.
"""

from __future__ import annotations

import re
import unicodedata

# Control chars except tab/newline; these leak in from binary→markdown
# conversions and break FTS5 / ripgrep.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# 3+ blank lines collapse to a single blank line.
_EXCESS_BLANK = re.compile(r"\n{3,}")
# Trailing whitespace on a line.
_TRAILING_WS = re.compile(r"[ \t]+(?=\n)")
# A markdown ATX heading line (capture the ``#`` run and the text). A real ATX
# heading requires whitespace (or end-of-line) after the ``#`` run; without that
# guard ``#!/bin/bash`` / ``#define`` / ``#nospace`` would be mis-detected and
# rewritten (mutating stored source + its sha). Matches the chunker's
# ``_HEADING_LINE`` (``^#{1,6}[ \t]+\S``), plus the bare ``#`` (EOL) case.
_HEADING = re.compile(r"^(#{1,6})(?:[ \t]+(.*?)[ \t]*#*[ \t]*)?$", re.MULTILINE)


def strip_control_chars(text: str) -> str:
    """Remove non-printing control characters (keeps ``\\t`` and ``\\n``)."""
    return _CONTROL_CHARS.sub("", text)


def normalize_whitespace(text: str) -> str:
    """Normalize newlines, trim trailing space, collapse excess blank lines."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _TRAILING_WS.sub("", text)
    text = _EXCESS_BLANK.sub("\n\n", text)
    return text


def normalize_headings(text: str) -> str:
    """Normalize ATX headings to ``#### text`` form (single space, no trailing
    ``#``)."""

    def _fix(m: re.Match[str]) -> str:
        hashes = m.group(1)
        body = (m.group(2) or "").strip()
        return f"{hashes} {body}" if body else hashes

    return _HEADING.sub(_fix, text)


def clean_markdown(text: str) -> str:
    """Full cleaning pipeline applied to converter output.

    NFC-normalizes unicode, strips control chars, normalizes whitespace and
    headings, and trims leading/trailing blank lines. Idempotent.
    """
    text = unicodedata.normalize("NFC", text)
    text = strip_control_chars(text)
    text = normalize_whitespace(text)
    text = normalize_headings(text)
    return text.strip("\n") + "\n" if text.strip() else ""
