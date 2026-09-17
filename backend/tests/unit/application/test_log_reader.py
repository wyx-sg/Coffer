"""``daemon.log`` is not one format, and the reader has to survive all of them.

Every fixture line here is a real shape taken from a live ``~/.coffer/logs/
daemon.log``: Coffer's own structlog JSON, the stdlib formatter the daemon
inherits once alembic configures logging, uvicorn's default, rich's panel
output from an upstream MCP server, and the zerolog the cloudflared child the
daemon respawns writes into the very same file. The parser used to understand
only the first of those, so the Activity page's time / level / logger columns
were empty for almost every row.
"""

from __future__ import annotations

import json
from datetime import datetime

from coffer.application.log_reader import (
    matches_level,
    parse_log_line,
    parse_log_lines,
    strip_ansi,
)


def test_a_structlog_json_line_stays_its_own_dict() -> None:
    line = json.dumps(
        {
            "event": "auto_sync_failed",
            "level": "warning",
            "timestamp": "2026-09-14T06:29:20.123456Z",
            "error": "git fetch failed",
        }
    )
    record = parse_log_line(line)
    assert record["level"] == "warning"
    assert record["event"] == "auto_sync_failed"
    assert record["error"] == "git fetch failed"


def test_the_stdlib_formatter_line_gives_up_its_level_and_logger() -> None:
    """`%(levelname)-5.5s [%(name)s] %(message)s` — the daemon's root format
    once a migration has run. The level arrives truncated to five characters."""
    record = parse_log_line(
        "WARNI [coffer.application.knowledge.skill_delivery] knowledge.skill_delivery.failed"
    )
    assert record["level"] == "warning"
    assert record["logger"] == "coffer.application.knowledge.skill_delivery"
    assert record["event"] == "knowledge.skill_delivery.failed"
    # It carries no time of its own — that formatter prints none. Saying so is
    # the point: the row must not claim a timestamp it never had.
    assert "timestamp" not in record


def test_an_info_line_keeps_its_padding_out_of_the_logger() -> None:
    record = parse_log_line(
        "INFO  [alembic.runtime.migration] Running upgrade 0073 -> 0074, name the machine"
    )
    assert record["level"] == "info"
    assert record["logger"] == "alembic.runtime.migration"
    assert record["event"] == "Running upgrade 0073 -> 0074, name the machine"


def test_the_cloudflared_child_writes_zerolog_into_the_same_file() -> None:
    record = parse_log_line(
        "2026-09-14T06:29:20Z INF precheck complete hard_fail=false suggested_protocol=quic"
    )
    assert record["timestamp"] == "2026-09-14T06:29:20Z"
    assert record["level"] == "info"
    assert record["event"] == "precheck complete hard_fail=false suggested_protocol=quic"


def test_zerolog_speaks_three_letter_levels() -> None:
    assert parse_log_line("2026-09-14T05:05:23Z ERR failed to serve incoming request")["level"] == (
        "error"
    )
    assert parse_log_line("2026-09-14T05:05:23Z WRN Serve tunnel error connIndex=1")["level"] == (
        "warning"
    )


def test_uvicorns_own_format_is_a_level_and_a_message() -> None:
    record = parse_log_line("ERROR:    ASGI callable returned without completing response.")
    assert record["level"] == "error"
    assert record["event"] == "ASGI callable returned without completing response."
    assert "logger" not in record


def test_a_dashed_formatter_line_gives_up_its_logger() -> None:
    record = parse_log_line(
        "WARNING - mcp_atlassian.utils.toolsets - TOOLSETS is not set — defaults to all toolsets"
    )
    assert record["level"] == "warning"
    assert record["logger"] == "mcp_atlassian.utils.toolsets"
    assert record["event"] == "TOOLSETS is not set — defaults to all toolsets"


def test_richs_local_wall_clock_becomes_the_instant_it_names() -> None:
    """rich prints the daemon's local time with no offset. The vault is one
    user on one machine, so the reader's zone is the writer's zone — and the
    row must render back to the wall clock the line actually printed."""
    record = parse_log_line("[09/10/26 17:53:12] INFO     Starting MCP server 'log-mcp'  s.py:209")
    assert record["level"] == "info"
    assert record["event"] == "Starting MCP server 'log-mcp'  s.py:209"
    back = datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00")).astimezone()
    assert back.strftime("%m/%d/%y %H:%M:%S") == "09/10/26 17:53:12"


def test_an_all_caps_word_that_is_not_a_level_is_not_read_as_one() -> None:
    record = parse_log_line("NOTE: the token file is gone")
    assert record == {"raw": "NOTE: the token file is gone"}


def test_a_line_no_writer_claims_is_kept_whole() -> None:
    record = parse_log_line("Will assume non-transactional DDL.")
    assert record == {"raw": "Will assume non-transactional DDL."}


# --- ANSI ---------------------------------------------------------------


#: A real line: the Codex app-server colours its stderr even into a pipe, and
#: the daemon relays it verbatim.
_ANSI_LINE = (
    "WARNI [coffer.infrastructure.chat.codex_app_server] codex app-server stderr: "
    "\x1b[2m2026-09-14T06:53:41.166917Z\x1b[0m \x1b[31mERROR\x1b[0m "
    "\x1b[2mcodex_models_manager::cache\x1b[0m\x1b[2m:\x1b[0m failed to load models cache"
)


def test_strip_ansi_removes_colour_without_touching_the_text() -> None:
    assert strip_ansi("\x1b[31mERROR\x1b[0m boom") == "ERROR boom"
    assert strip_ansi("plain") == "plain"


def test_a_colour_escaped_line_still_parses_and_shows_no_escapes() -> None:
    record = parse_log_line(_ANSI_LINE)
    assert record["level"] == "warning"
    assert record["logger"] == "coffer.infrastructure.chat.codex_app_server"
    assert "\x1b" not in record["event"]
    assert "[31m" not in record["event"]
    assert record["event"].startswith("codex app-server stderr: 2026-09-14T06:53:41.166917Z ERROR")


def test_colour_at_the_head_of_a_line_does_not_hide_its_level() -> None:
    record = parse_log_line("\x1b[31mERROR\x1b[0m:    the upstream went away")
    assert record["level"] == "error"
    assert record["event"] == "the upstream went away"


# --- continuation lines -------------------------------------------------


_TRACEBACK = [
    "ERROR [coffer.memory.consolidate] consolidate.store.failed store=project-61Z8Q9",
    "Traceback (most recent call last):",
    '  File "coffer/application/memory/consolidate.py", line 159, in run',
    "    raw = await self._llm.complete(",
    "          ^^^^^^^^^^^^^^^^^^^^^^^^^",
    "openai.RateLimitError: Error code: 429 - rate limit reached",
    "2026-09-14T06:29:20Z INF Registered tunnel connection connIndex=1",
]


def test_a_traceback_belongs_to_the_record_that_raised_it() -> None:
    records = parse_log_lines(_TRACEBACK)
    assert len(records) == 2  # the ERROR (with its traceback) and the tunnel line
    failed, tunnel = records
    assert failed["event"] == "consolidate.store.failed store=project-61Z8Q9"
    assert failed["continuation"] == _TRACEBACK[1:6]
    assert tunnel["event"] == "Registered tunnel connection connIndex=1"
    assert "continuation" not in tunnel


def test_the_exception_line_closes_the_traceback() -> None:
    """The final ``SomeError: …`` is not indented, so only the block it ends
    keeps it — a plain line after it starts a record of its own."""
    records = parse_log_lines([*_TRACEBACK[:6], "Will assume non-transactional DDL."])
    assert len(records) == 2
    assert records[1] == {"raw": "Will assume non-transactional DDL."}


def test_a_wrapped_rich_panel_does_not_become_a_row_each() -> None:
    records = parse_log_lines(
        [
            "[09/10/26 17:53:12] INFO     Starting MCP server 'Atlassian MCP'  server.py:2506",
            "                             with transport 'stdio'",
            "╭────────────────────────────────╮",
            "│            FastMCP  2.0        │",
            "╰────────────────────────────────╯",
        ]
    )
    assert len(records) == 1
    assert len(records[0]["continuation"]) == 4


def test_a_tail_that_opens_mid_traceback_keeps_the_orphan_lines() -> None:
    """The window is bounded, so the record that raised may be off the top.
    Its frames must still be readable rather than dropped."""
    records = parse_log_lines(
        ['  File "coffer/app.py", line 12, in run', "    raise ValueError(name)"]
    )
    assert len(records) == 1
    assert records[0]["raw"] == '  File "coffer/app.py", line 12, in run'
    assert records[0]["continuation"] == ["    raise ValueError(name)"]


def test_blank_lines_are_not_records() -> None:
    assert parse_log_lines(["", "   ", "ERROR:    boom"]) == [{"level": "error", "event": "boom"}]


# --- errors_only --------------------------------------------------------


def test_errors_only_now_judges_every_writer_by_its_own_level() -> None:
    """Before, every non-JSON line counted as an error, which meant the filter
    kept the whole file. A zerolog INF line is an info line."""
    assert not matches_level(parse_log_line("2026-09-14T06:29:20Z INF Starting tunnel"), True)
    assert matches_level(parse_log_line("2026-09-14T05:05:23Z ERR Connection terminated"), True)
    assert matches_level(parse_log_line("CRITI [coffer.daemon] out of disk"), True)


def test_a_line_with_no_readable_level_survives_errors_only() -> None:
    """Not knowing what a line was is not evidence that it was harmless."""
    assert matches_level(parse_log_line("Will assume non-transactional DDL."), True)


def test_nothing_is_filtered_when_errors_only_is_off() -> None:
    assert matches_level(parse_log_line("2026-09-14T06:29:20Z INF Starting tunnel"), False)
