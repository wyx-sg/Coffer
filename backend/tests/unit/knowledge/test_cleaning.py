"""Unit tests for the markdown cleaning pipeline. Pure — no I/O."""

from coffer.infrastructure.knowledge.cleaning import (
    clean_markdown,
    normalize_headings,
    normalize_whitespace,
    strip_control_chars,
)


def test_strip_control_chars_keeps_tab_and_newline() -> None:
    assert strip_control_chars("a\x00b\x07c\td\ne") == "abc\td\ne"


def test_normalize_whitespace_collapses_blank_lines_and_crlf() -> None:
    out = normalize_whitespace("a\r\n\r\n\r\n\r\nb   \nc")
    assert out == "a\n\nb\nc"


def test_normalize_headings_trims_and_spaces() -> None:
    assert normalize_headings("## Title ##") == "## Title"
    assert normalize_headings("#   Hello   ") == "# Hello"


def test_normalize_headings_leaves_hash_lines_without_space_untouched() -> None:
    """A real ATX heading requires whitespace after the ``#`` run. Lines like a
    shebang or a C ``#define`` must NOT be rewritten (would mutate source + sha),
    while genuine headings are still normalized."""
    # No space after the hashes ⇒ not a heading ⇒ unchanged.
    assert normalize_headings("#!/bin/bash") == "#!/bin/bash"
    assert normalize_headings("#define FOO 1") == "#define FOO 1"
    assert normalize_headings("#nospace") == "#nospace"
    assert normalize_headings("##Title ##") == "##Title ##"
    # A bare ``#`` (no body) is left as-is, not turned into ``# ``.
    assert normalize_headings("#") == "#"
    # Genuine ATX headings still normalize.
    assert normalize_headings("###   Deep   ###") == "### Deep"
    # Multi-line: shebang preserved, heading normalized.
    src = "#!/bin/bash\n##Heading\n## Real Heading\n#define X"
    assert normalize_headings(src) == "#!/bin/bash\n##Heading\n## Real Heading\n#define X"


def test_clean_markdown_is_idempotent() -> None:
    raw = "#  Title  \n\n\n\nbody\x07 text\r\n"
    once = clean_markdown(raw)
    assert clean_markdown(once) == once
    assert once.endswith("\n")
    assert "\x07" not in once


def test_clean_markdown_empty_input() -> None:
    assert clean_markdown("   \n\n  ") == ""
