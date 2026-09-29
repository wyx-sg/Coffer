"""The structure pass over a finished reply (spec channels "Shape a reply for
what the chat can show")."""

from __future__ import annotations

import pytest

from coffer.application.channel.reply_shape import shape_reply, split_details

_SMALL_TABLE = """Three jobs ran.

| job | state | why |
|-----|:-----:|-----|
| checkout | failed | 3DS timeout |
| search | ok | |

That is all."""


@pytest.mark.acceptance(
    spec="channels", scenario="a table becomes bullet rows where the chat cannot show tables"
)
def test_a_small_table_becomes_one_bullet_per_row() -> None:
    shaped = shape_reply(_SMALL_TABLE, renders_tables=False)

    assert shaped.body == (
        "Three jobs ran.\n\n"
        "- **checkout** · failed · 3DS timeout\n- **search** · ok\n\n"
        "That is all."
    )
    assert shaped.files == ()


def test_a_big_table_keeps_five_rows_and_goes_out_whole_as_a_csv() -> None:
    rows = "\n".join(f"| job{i} | ok |" for i in range(20))
    shaped = shape_reply(f"| job | state |\n|---|---|\n{rows}", renders_tables=False)

    lines = shaped.body.splitlines()
    assert lines[:5] == [f"- **job{i}** · ok" for i in range(5)]
    assert lines[5] == "*… 20 rows in table-1.csv*"
    [csv_file] = shaped.files
    assert csv_file.filename == "table-1.csv"
    assert csv_file.content.splitlines()[:2] == ["job,state", "job0,ok"]


@pytest.mark.acceptance(spec="channels", scenario="a long log is attached as a file")
def test_a_long_code_block_keeps_three_lines_and_is_attached() -> None:
    log = "\n".join(f"line {i}" for i in range(40))
    shaped = shape_reply(f"Here it is:\n\n```log\n{log}\n```\n\nDone.", max_inline_code_lines=30)

    assert shaped.body == (
        "Here it is:\n\n```log\nline 0\nline 1\nline 2\n```\n*… 40 lines in log-1.log*\n\nDone."
    )
    assert shaped.files[0].filename == "log-1.log"
    assert shaped.files[0].content == log + "\n"


def test_a_diff_keeps_its_suffix_and_a_short_block_is_left_alone() -> None:
    diff = "\n".join(f"+{i}" for i in range(31))
    assert shape_reply(f"```diff\n{diff}\n```", max_inline_code_lines=30).files[0].filename == (
        "log-1.diff"
    )
    short = "```\na\nb\n```"
    assert shape_reply(short, max_inline_code_lines=30).body == short


def test_a_table_inside_a_code_block_is_code_not_a_table() -> None:
    text = "```\n| a | b |\n|---|---|\n| 1 | 2 |\n```"
    assert shape_reply(text, renders_tables=False).body == text


def test_a_transport_that_shows_everything_gets_the_reply_untouched() -> None:
    assert shape_reply(_SMALL_TABLE).body == _SMALL_TABLE


def test_the_details_section_is_split_off_its_heading() -> None:
    head, details = split_details("Deploy is green.\n\n## Details\n\n- step one\n- step two")
    assert head == "Deploy is green."
    assert details == "- step one\n- step two"
    assert split_details("no details here") == ("no details here", "")
