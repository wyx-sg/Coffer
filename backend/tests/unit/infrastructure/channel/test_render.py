"""Outbound rendering: markdown → Telegram HTML, plus chunking."""

from __future__ import annotations

from coffer.infrastructure.channel.render import chunk_text, markdown_to_telegram_html


class TestMarkdownToTelegramHtml:
    def test_plain_text_passes_through(self):
        assert markdown_to_telegram_html("hello world") == "hello world"

    def test_bold(self):
        assert markdown_to_telegram_html("a **bold** word") == "a <b>bold</b> word"

    def test_italic_asterisk_and_underscore(self):
        assert markdown_to_telegram_html("an *em* word") == "an <i>em</i> word"
        assert markdown_to_telegram_html("an _em_ word") == "an <i>em</i> word"

    def test_bold_is_not_eaten_by_italic(self):
        assert markdown_to_telegram_html("**strong**") == "<b>strong</b>"

    def test_inline_code(self):
        assert markdown_to_telegram_html("run `coffer up` now") == "run <code>coffer up</code> now"

    def test_inline_code_protects_markdown_and_escapes_content(self):
        assert markdown_to_telegram_html("`**a** < b`") == "<code>**a** &lt; b</code>"

    def test_code_fence_with_language(self):
        rendered = markdown_to_telegram_html("before\n```python\nx < 1 & y\n```\nafter")
        assert rendered == "before\n<pre>x &lt; 1 &amp; y</pre>\nafter"

    def test_code_fence_without_language(self):
        assert markdown_to_telegram_html("```\nplain\n```") == "<pre>plain</pre>"

    def test_link(self):
        rendered = markdown_to_telegram_html("see [docs](https://example.com/x)")
        assert rendered == 'see <a href="https://example.com/x">docs</a>'

    def test_non_http_link_left_as_text(self):
        assert markdown_to_telegram_html("[x](ftp://e.com)") == "[x](ftp://e.com)"

    def test_heading_becomes_bold(self):
        assert markdown_to_telegram_html("## Title\nbody") == "<b>Title</b>\nbody"

    def test_special_chars_escaped_outside_code(self):
        assert markdown_to_telegram_html("a < b & c > d") == "a &lt; b &amp; c &gt; d"

    def test_raw_html_cannot_inject_tags(self):
        assert markdown_to_telegram_html("<script>x</script>") == "&lt;script&gt;x&lt;/script&gt;"

    def test_newlines_preserved_so_multiline_output_stays_multiline(self):
        # Telegram renders \n literally (HTML parse_mode), so the web-only
        # single-newline collapse must NOT happen here — each line stays its own
        # line, keeping multi-fact agent output (e.g. /usage) readable.
        rendered = markdown_to_telegram_html("line one\nline two\nline three")
        assert rendered == "line one\nline two\nline three"

    def test_dash_bullets_become_glyphs(self):
        assert markdown_to_telegram_html("- one\n- two") == "• one\n• two"

    def test_star_bullets_become_glyphs(self):
        assert markdown_to_telegram_html("* one\n* two") == "• one\n• two"

    def test_indented_bullet_keeps_indent(self):
        # The whole message is stripped at the edges, so put the nested item mid-text.
        assert markdown_to_telegram_html("top\n  - nested") == "top\n  • nested"

    def test_bullet_glyph_does_not_eat_bold_or_italic(self):
        # Leading **bold** / *italic* are not list markers (no space after *).
        assert markdown_to_telegram_html("**strong** lead") == "<b>strong</b> lead"
        assert markdown_to_telegram_html("*em* lead") == "<i>em</i> lead"

    def test_empty_input_renders_empty(self):
        assert markdown_to_telegram_html("") == ""


class TestChunkText:
    def test_empty_input_yields_no_chunks(self):
        assert chunk_text("", 100) == []
        assert chunk_text("   \n\n  ", 100) == []

    def test_short_text_single_chunk(self):
        assert chunk_text("hello", 100) == ["hello"]

    def test_text_exactly_at_limit_single_chunk(self):
        assert chunk_text("abcd", 4) == ["abcd"]

    def test_splits_on_paragraph_boundary(self):
        assert chunk_text("aaa\n\nbbb", 4) == ["aaa", "bbb"]

    def test_packs_paragraphs_under_limit_into_one_chunk(self):
        assert chunk_text("aa\n\nbb\n\nccccc", 7) == ["aa\n\nbb", "ccccc"]

    def test_oversize_single_paragraph_hard_split(self):
        assert chunk_text("abcdefghij", 4) == ["abcd", "efgh", "ij"]

    def test_oversize_paragraph_flushes_accumulated_chunk_first(self):
        assert chunk_text("aa\n\nabcdefgh", 4) == ["aa", "abcd", "efgh"]

    def test_chunks_all_non_empty_and_within_limit(self):
        text = "para one is long\n\n" * 5 + "x" * 25
        chunks = chunk_text(text, 20)
        assert len(chunks) >= 2
        assert all(chunks)
        assert all(len(c) <= 20 for c in chunks)
        assert "".join(chunks).count("x") == 25  # nothing dropped
