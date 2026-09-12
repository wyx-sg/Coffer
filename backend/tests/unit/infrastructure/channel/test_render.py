"""Outbound rendering: markdown → Telegram HTML / SeaTalk markdown, plus chunking."""

from __future__ import annotations

import pytest

from coffer.infrastructure.channel.render import (
    chunk_text,
    escape_seatalk_literal,
    markdown_to_seatalk,
    markdown_to_telegram_html,
    split_leading_mention,
)

#: The two documented SeaTalk mention forms, each built with a target the marker
#: escaper WOULD mangle if it were allowed near them: an id holding `_`, and an
#: address holding `_` the way ordinary work addresses do.
_MENTION_BY_ID = '<mention-tag target="seatalk://user?id=abc_def"/>'
_MENTION_BY_EMAIL = '<mention-tag target="seatalk://user?email=first_last@example.com"/>'


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


class TestMarkdownToSeatalk:
    """SeaTalk has its own markdown (``format: 1``): bold, italic, inline code,
    fences and lists are native; headings and links are not; a literal marker
    character is escaped with a SINGLE backslash."""

    def test_plain_text_passes_through(self):
        assert markdown_to_seatalk("hello world") == "hello world"

    def test_bold_and_inline_code_are_native(self):
        assert markdown_to_seatalk("**bold** and `code`") == "**bold** and `code`"

    @pytest.mark.acceptance(
        spec="channels", scenario="seatalk markdown escapes a literal marker character"
    )
    def test_stray_markers_are_escaped_with_a_single_backslash(self):
        # `snake_case` must survive as typed instead of being read as markup.
        # One backslash, never two: SeaTalk eats the first and renders the
        # second, which is how `claude_code` reached a real chat as
        # `claude\_code`.
        assert markdown_to_seatalk("run some_var now") == "run some\\_var now"
        assert markdown_to_seatalk("5*6 = 30") == "5\\*6 = 30"
        assert markdown_to_seatalk("a ~~b~~ c") == "a \\~\\~b\\~\\~ c"

    def test_angle_brackets_are_left_alone(self):
        # Verified by live probe: SeaTalk delivers them as written, so the
        # `/model <name>` hint on a selection card needs no escaping.
        assert markdown_to_seatalk("send /model <name>") == "send /model <name>"

    def test_code_span_content_is_never_escaped(self):
        assert markdown_to_seatalk("`a_b`") == "`a_b`"

    def test_code_fence_is_kept_as_a_fence(self):
        assert markdown_to_seatalk("```python\nx = a_b\n```") == "```\nx = a_b\n```"

    def test_heading_becomes_bold(self):
        assert markdown_to_seatalk("## Title\nbody") == "**Title**\nbody"

    def test_link_becomes_label_and_url(self):
        rendered = markdown_to_seatalk("see [docs](https://example.com/a_b)")
        assert rendered == "see docs (https://example.com/a_b)"

    def test_bare_url_keeps_its_underscores(self):
        assert markdown_to_seatalk("go to https://e.com/a_b now") == "go to https://e.com/a_b now"

    def test_star_and_plus_bullets_become_the_dash_form(self):
        assert markdown_to_seatalk("* one\n+ two\n- three") == "- one\n- two\n- three"

    def test_ordered_and_indented_lists_are_left_alone(self):
        assert markdown_to_seatalk("1. one\n2. two") == "1. one\n2. two"
        assert markdown_to_seatalk("- one\n    - nested") == "- one\n    - nested"

    def test_underscore_italic_becomes_the_asterisk_form(self):
        # SeaTalk's underscore italic needs surrounding spaces; the asterisk form
        # does not, so normalise to the one that always renders.
        assert markdown_to_seatalk("an _em_ word") == "an *em* word"

    def test_empty_input_renders_empty(self):
        assert markdown_to_seatalk("") == ""

    @pytest.mark.acceptance(
        spec="channels",
        scenario="a mention target survives the markdown escaper unchanged",
    )
    def test_a_mention_tag_is_never_escaped_whatever_its_target_holds(self):
        # An id with an underscore used to arrive as
        # `...id=abc\_def..."/>` — visible tag source instead of a name. The
        # email form of the tag makes it the normal case, not the edge one, so
        # the renderer lifts the tag out of the escaping pass entirely.
        assert markdown_to_seatalk(f"{_MENTION_BY_ID} hi") == f"{_MENTION_BY_ID} hi"
        assert markdown_to_seatalk(f"{_MENTION_BY_EMAIL} hi") == f"{_MENTION_BY_EMAIL} hi"
        # And the text around it is still escaped as it always was.
        assert (
            markdown_to_seatalk(f"{_MENTION_BY_ID} run some_var")
            == f"{_MENTION_BY_ID} run some\\_var"
        )


class TestEscapeSeaTalkLiteral:
    """An in-flight stream snapshot: a reply clipped mid-word, which has to reach
    the chat AS WRITTEN inside a ``format: 1`` message (that message carries the
    @mention, and a mention is only a name in a rich one)."""

    @pytest.mark.acceptance(
        spec="channels",
        scenario="an interim snapshot reaches the chat as written, not as markup",
    )
    def test_partial_markup_is_escaped_rather_than_left_to_the_parser(self):
        # A reply cut mid-word can end inside an unclosed run. Escaped, the
        # reader sees the characters; unescaped, the client renders noise.
        assert escape_seatalk_literal("I found **bo") == "I found \\*\\*bo"
        assert escape_seatalk_literal("an _em") == "an \\_em"
        assert escape_seatalk_literal("a `cod") == "a \\`cod"

    def test_one_backslash_per_marker_never_two(self):
        # Two would be one escape too many: SeaTalk eats the first and shows the
        # second, which is how `claude_code` once reached a real chat as
        # `claude\_code`.
        escaped = escape_seatalk_literal("some_var")
        assert escaped == "some\\_var"
        assert "\\\\" not in escaped

    def test_a_mention_tag_passes_through_untouched(self):
        assert escape_seatalk_literal(f"{_MENTION_BY_ID} **bo") == f"{_MENTION_BY_ID} \\*\\*bo"
        assert escape_seatalk_literal(_MENTION_BY_EMAIL) == _MENTION_BY_EMAIL

    def test_text_with_nothing_to_escape_is_unchanged(self):
        assert escape_seatalk_literal("⏳ Got it — working on this…") == (
            "⏳ Got it — working on this…"
        )


class TestSplitLeadingMention:
    """Shortening a snapshot from the front must not eat the mention the message
    is notifying on, so the prefix comes off first and goes back on after."""

    def test_the_prefix_includes_the_space_that_follows_it(self):
        prefix, rest = split_leading_mention(f"{_MENTION_BY_ID} the answer")
        assert prefix == f"{_MENTION_BY_ID} "
        assert rest == "the answer"
        assert prefix + rest == f"{_MENTION_BY_ID} the answer"

    def test_text_without_a_mention_is_all_body(self):
        assert split_leading_mention("the answer") == ("", "the answer")
        # A tag that is not at the head is body: only an opening mention is the
        # one the platform notifies on.
        assert split_leading_mention(f"hi {_MENTION_BY_ID}") == ("", f"hi {_MENTION_BY_ID}")


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
