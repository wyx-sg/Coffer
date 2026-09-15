"""Unit tests for FileTranscriptReader search/filter/sort + the summary cache.

Every test builds its own transcript tree under ``tmp_path``; the reader is
never pointed at a real ``~/.claude`` or ``~/.codex``, and the root conftest
pins ``$COFFER_AGENT_STATE_ROOT`` per test so the sidecar it writes is this
test's own.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from coffer.domain.agent.transcripts import UnsupportedAgentTypeError
from coffer.infrastructure.agent import paths
from coffer.infrastructure.agent.transcript_reader import FileTranscriptReader


def _counting_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[FileTranscriptReader, dict[str, int]]:
    """A reader whose ``_parse_file`` calls are counted — how every cache test
    here tells "served from the cache" apart from "parsed again"."""
    r = FileTranscriptReader()
    calls = {"n": 0}
    orig = r._parse_file

    def counting(agent_type_value: str, path: Path):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return orig(agent_type_value, path)

    monkeypatch.setattr(r, "_parse_file", counting)
    return r, calls


def _codex_session(
    path: Path, *, sid: str, cwd: str, ts_start: str, ts_end: str, user_text: str
) -> None:
    lines = [
        json.dumps(
            {"timestamp": ts_start, "type": "session_meta", "payload": {"id": sid, "cwd": cwd}}
        ),
        json.dumps(
            {
                "timestamp": ts_start,
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_text}],
                },
            }
        ),
        json.dumps(
            {
                "timestamp": ts_end,
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "ok"}],
                },
            }
        ),
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _make_codex_tree(root: Path) -> Path:
    """Three sessions; session 'a' runs long so last_activity order ≠ start order."""
    d = root / "sessions" / "2026" / "05"
    d.mkdir(parents=True)
    _codex_session(
        d / "rollout-a.jsonl",
        sid="a",
        cwd="/proj/alpha",
        ts_start="2026-05-01T00:00:00Z",
        ts_end="2026-05-09T00:00:00Z",
        user_text="fix the alpha login bug",
    )
    _codex_session(
        d / "rollout-b.jsonl",
        sid="b",
        cwd="/proj/beta",
        ts_start="2026-05-02T00:00:00Z",
        ts_end="2026-05-02T02:00:00Z",
        user_text="add beta dashboard",
    )
    _codex_session(
        d / "rollout-c.jsonl",
        sid="c",
        cwd="/proj/alpha",
        ts_start="2026-05-03T00:00:00Z",
        ts_end="2026-05-03T00:30:00Z",
        user_text="refactor alpha payments",
    )
    return d


def test_missing_sessions_dir_is_empty_not_an_error(tmp_path: Path) -> None:
    r = FileTranscriptReader()
    total, page = r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    assert (total, page) == (0, [])


def test_unknown_agent_type_is_rejected(tmp_path: Path) -> None:
    r = FileTranscriptReader()
    with pytest.raises(UnsupportedAgentTypeError):
        r.search_session_summaries(
            agent_type_value="nonexistent", config_dir=str(tmp_path), limit=10, offset=0
        )


def test_lists_every_session_with_summary_fields(tmp_path: Path) -> None:
    _make_codex_tree(tmp_path)
    r = FileTranscriptReader()
    total, page = r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    assert total == 3
    by_id = {s.session_id: s for s in page}
    a = by_id["a"]
    assert a.title == "fix the alpha login bug"
    assert a.project_path == "/proj/alpha"
    assert a.message_count == 2
    assert a.source_path.endswith("rollout-a.jsonl")


def test_non_jsonl_files_are_ignored(tmp_path: Path) -> None:
    d = _make_codex_tree(tmp_path)
    (d / "notes.md").write_text("not a transcript", encoding="utf-8")
    r = FileTranscriptReader()
    total, _ = r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    assert total == 3


def test_search_matches_title_or_project(tmp_path: Path) -> None:
    _make_codex_tree(tmp_path)
    r = FileTranscriptReader()
    total, page = r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), query="alpha", limit=100, offset=0
    )
    assert total == 2
    assert {s.session_id for s in page} == {"a", "c"}


def test_search_is_case_insensitive(tmp_path: Path) -> None:
    _make_codex_tree(tmp_path)
    r = FileTranscriptReader()
    total, page = r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), query="BETA", limit=100, offset=0
    )
    assert total == 1
    assert page[0].session_id == "b"


def test_filter_by_project_exact(tmp_path: Path) -> None:
    _make_codex_tree(tmp_path)
    r = FileTranscriptReader()
    total, page = r.search_session_summaries(
        agent_type_value="codex",
        config_dir=str(tmp_path),
        project="/proj/alpha",
        limit=100,
        offset=0,
    )
    assert total == 2
    assert {s.session_id for s in page} == {"a", "c"}


def test_sort_by_started_at_asc_and_desc(tmp_path: Path) -> None:
    _make_codex_tree(tmp_path)
    r = FileTranscriptReader()
    _, asc = r.search_session_summaries(
        agent_type_value="codex",
        config_dir=str(tmp_path),
        sort="started_at",
        order="asc",
        limit=100,
        offset=0,
    )
    assert [s.session_id for s in asc] == ["a", "b", "c"]
    _, desc = r.search_session_summaries(
        agent_type_value="codex",
        config_dir=str(tmp_path),
        sort="started_at",
        order="desc",
        limit=100,
        offset=0,
    )
    assert [s.session_id for s in desc] == ["c", "b", "a"]


def test_sort_by_message_count(tmp_path: Path) -> None:
    d = _make_codex_tree(tmp_path)
    # Give 'b' a third turn so it outranks the others by message count.
    with (d / "rollout-b.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(
            "\n"
            + json.dumps(
                {
                    "timestamp": "2026-05-02T03:00:00Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "one more"}],
                    },
                }
            )
        )
    r = FileTranscriptReader()
    _, page = r.search_session_summaries(
        agent_type_value="codex",
        config_dir=str(tmp_path),
        sort="message_count",
        order="desc",
        limit=100,
        offset=0,
    )
    assert page[0].session_id == "b"
    assert page[0].message_count == 3


def test_default_sort_is_last_activity_desc(tmp_path: Path) -> None:
    _make_codex_tree(tmp_path)
    r = FileTranscriptReader()
    _, page = r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    # a ends 05-09 (latest), c ends 05-03, b ends 05-02
    assert [s.session_id for s in page] == ["a", "c", "b"]


def test_pagination_limit_offset(tmp_path: Path) -> None:
    _make_codex_tree(tmp_path)
    r = FileTranscriptReader()
    total, page = r.search_session_summaries(
        agent_type_value="codex",
        config_dir=str(tmp_path),
        sort="started_at",
        order="asc",
        limit=1,
        offset=1,
    )
    assert total == 3  # total is the MATCHED count, not the page length
    assert [s.session_id for s in page] == ["b"]


def test_unreadable_file_is_skipped_not_fatal(tmp_path: Path) -> None:
    d = _make_codex_tree(tmp_path)
    broken = d / "rollout-broken.jsonl"
    broken.write_bytes(b"\x00\x01\x02")
    r = FileTranscriptReader()
    total, _ = r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    # The binary file parses to an empty session rather than killing the listing.
    assert total == 4


def test_cache_reparses_only_changed_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d = _make_codex_tree(tmp_path)
    r, calls = _counting_reader(monkeypatch)

    r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    assert calls["n"] == 3  # all parsed on first call

    r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    assert calls["n"] == 3  # full cache hit; nothing re-parsed

    p = d / "rollout-b.jsonl"
    st = p.stat()
    os.utime(p, (st.st_atime, st.st_mtime + 10))  # bump mtime
    r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    assert calls["n"] == 4  # only the changed file re-parsed


def test_cache_reparses_when_size_changes_under_the_same_mtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Size is half the stamp because mtime alone has a filesystem's timestamp
    granularity underneath it, and appending to a live transcript is exactly the
    write that can land inside one tick."""
    d = _make_codex_tree(tmp_path)
    r, calls = _counting_reader(monkeypatch)
    r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    assert calls["n"] == 3

    p = d / "rollout-b.jsonl"
    before = p.stat()
    with p.open("a", encoding="utf-8") as fh:
        fh.write("\n" + json.dumps({"timestamp": "2026-05-02T04:00:00Z", "type": "turn_context"}))
    os.utime(p, (before.st_atime, before.st_mtime))  # pin mtime; only size moved
    assert p.stat().st_mtime == before.st_mtime

    r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    assert calls["n"] == 4


def test_cache_prunes_entries_for_deleted_files(tmp_path: Path) -> None:
    d = _make_codex_tree(tmp_path)
    r = FileTranscriptReader()
    r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    assert len(r._cache) == 3
    (d / "rollout-b.jsonl").unlink()
    total, _ = r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    assert total == 2
    assert len(r._cache) == 2  # the deleted file's entry is gone, not leaked
    # …and the sidecar it was written back to does not leak it either.
    assert len(json.loads(paths.transcript_summaries_path().read_text())) == 2


# ---------------------------------------------------------------------------
# The sidecar: the cache that survives a daemon restart
# ---------------------------------------------------------------------------


def test_sidecar_survives_a_restart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A second reader is what a restarted daemon has. It must parse nothing."""
    _make_codex_tree(tmp_path)
    first, first_calls = _counting_reader(monkeypatch)
    _, before = first.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    assert first_calls["n"] == 3

    second, second_calls = _counting_reader(monkeypatch)
    total, after = second.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    assert second_calls["n"] == 0
    assert total == 3
    assert after == before  # every summary field round-tripped, not just the ids


def test_second_pass_that_changed_nothing_does_not_rewrite_the_sidecar(tmp_path: Path) -> None:
    _make_codex_tree(tmp_path)
    r = FileTranscriptReader()
    r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    sidecar = paths.transcript_summaries_path()
    stamp = sidecar.stat().st_mtime_ns
    os.utime(sidecar, ns=(stamp - 10**9, stamp - 10**9))  # detectably older
    r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    assert sidecar.stat().st_mtime_ns == stamp - 10**9


def test_missing_sidecar_still_lists_correctly(tmp_path: Path) -> None:
    _make_codex_tree(tmp_path)
    baseline = FileTranscriptReader().search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    paths.transcript_summaries_path().unlink()
    assert (
        FileTranscriptReader().search_session_summaries(
            agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
        )
        == baseline
    )


@pytest.mark.parametrize(
    "content",
    [
        "",  # empty — a truncated write, or a file someone touched
        "{ not json at all",  # corrupt
        "[1, 2, 3]",  # valid JSON, wrong shape
        '{"/gone.jsonl": {"mtime": "yesterday"}}',  # right shape, unusable entry
    ],
)
def test_unusable_sidecar_still_lists_correctly(tmp_path: Path, content: str) -> None:
    """Never a wrong answer, only a slower one — the sidecar is disposable."""
    _make_codex_tree(tmp_path)
    baseline = FileTranscriptReader().search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    paths.transcript_summaries_path().write_text(content, encoding="utf-8")
    assert (
        FileTranscriptReader().search_session_summaries(
            agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
        )
        == baseline
    )


def test_sidecar_entry_is_dropped_when_the_file_changed_since(tmp_path: Path) -> None:
    """A stale stamp must re-parse, or a restart would serve yesterday's summary."""
    d = _make_codex_tree(tmp_path)
    FileTranscriptReader().search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    _codex_session(
        d / "rollout-b.jsonl",
        sid="b",
        cwd="/proj/beta",
        ts_start="2026-05-02T00:00:00Z",
        ts_end="2026-05-02T02:00:00Z",
        user_text="rewritten beta prompt",
    )
    _, page = FileTranscriptReader().search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    assert {s.session_id: s.title for s in page}["b"] == "rewritten beta prompt"


def test_sidecar_keeps_another_agent_root_untouched(tmp_path: Path) -> None:
    """One agent's pass must not prune the other's entries out of the shared file."""
    _make_codex_tree(tmp_path)
    other = tmp_path / "other"
    (other / "sessions").mkdir(parents=True)
    _codex_session(
        other / "sessions" / "rollout-z.jsonl",
        sid="z",
        cwd="/proj/zeta",
        ts_start="2026-05-04T00:00:00Z",
        ts_end="2026-05-04T01:00:00Z",
        user_text="zeta work",
    )
    r = FileTranscriptReader()
    r.search_session_summaries(agent_type_value="codex", config_dir=str(other), limit=100, offset=0)
    r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    stored = json.loads(paths.transcript_summaries_path().read_text())
    assert len(stored) == 4  # three here, one under the other root
