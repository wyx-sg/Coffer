"""Integration tests for the OpenCode storage-tree transcript reader (spec 007)."""

from __future__ import annotations

import json
import pathlib

import pytest

from coffer.infrastructure.distill.opencode_reader import (
    opencode_storage_dir,
    parse_opencode_storage,
)
from coffer.infrastructure.distill.transcript_reader import FileTranscriptReader


def _write(path: pathlib.Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


@pytest.fixture
def storage(tmp_path: pathlib.Path) -> pathlib.Path:
    """A realistic OpenCode storage tree:

    one project, one session, a user + assistant message; the assistant message
    has a text part AND a tool part (whose payload must never surface).
    """
    root = tmp_path / "opencode" / "storage"
    _write(root / "project" / "proj1.json", {"id": "proj1", "directory": "/work/myrepo"})
    _write(
        root / "session" / "proj1" / "sess1.json",
        {"id": "sess1", "title": "fix the bug", "time": {"created": 1_700_000_000_000}},
    )
    _write(
        root / "message" / "sess1" / "msg1.json",
        {"id": "msg1", "role": "user", "time": {"created": 1_700_000_000_001}},
    )
    _write(
        root / "message" / "sess1" / "msg2.json",
        {"id": "msg2", "role": "assistant", "time": {"created": 1_700_000_000_002}},
    )
    _write(
        root / "part" / "msg1" / "prt1.json",
        {"id": "prt1", "type": "text", "text": "hello opencode"},
    )
    _write(
        root / "part" / "msg2" / "prt1.json", {"id": "prt1", "type": "text", "text": "Hi! Done."}
    )
    _write(
        root / "part" / "msg2" / "prt2.json",
        {
            "id": "prt2",
            "type": "tool",
            "tool": "bash",
            "state": {"input": {"command": "SECRET_VAL"}},
        },
    )
    return root


def test_parse_reconstructs_session(storage: pathlib.Path) -> None:
    sessions = parse_opencode_storage(storage)
    assert len(sessions) == 1
    s = sessions[0]
    assert s.session_id == "sess1"
    assert s.agent_type_value == "opencode"
    assert s.project_path == "/work/myrepo"
    assert s.started_at is not None
    assert [(m.role, m.text) for m in s.messages] == [
        ("user", "hello opencode"),
        ("assistant", "Hi! Done."),
    ]


def test_tool_part_payload_never_surfaces(storage: pathlib.Path) -> None:
    sessions = parse_opencode_storage(storage)
    all_text = " ".join(m.text for s in sessions for m in s.messages)
    assert "SECRET_VAL" not in all_text


def test_messages_ordered_by_created_time(tmp_path: pathlib.Path) -> None:
    root = tmp_path / "opencode" / "storage"
    _write(root / "session" / "p" / "s.json", {"id": "s", "directory": "/d"})
    # Write out of order; the reader must sort by time.created.
    _write(
        root / "message" / "s" / "b.json", {"id": "b", "role": "assistant", "time": {"created": 20}}
    )
    _write(root / "message" / "s" / "a.json", {"id": "a", "role": "user", "time": {"created": 10}})
    _write(root / "part" / "a" / "1.json", {"id": "1", "type": "text", "text": "first"})
    _write(root / "part" / "b" / "1.json", {"id": "1", "type": "text", "text": "second"})
    s = parse_opencode_storage(root)[0]
    assert [m.text for m in s.messages] == ["first", "second"]


def test_project_directory_falls_back_to_session_field(tmp_path: pathlib.Path) -> None:
    """When there is no project file, the session's own ``directory`` is used."""
    root = tmp_path / "opencode" / "storage"
    _write(root / "session" / "global" / "s.json", {"id": "s", "directory": "/from/session"})
    _write(root / "message" / "s" / "m.json", {"id": "m", "role": "user", "time": {"created": 1}})
    _write(root / "part" / "m" / "p.json", {"id": "p", "type": "text", "text": "hi"})
    s = parse_opencode_storage(root)[0]
    assert s.project_path == "/from/session"


def test_missing_storage_returns_empty(tmp_path: pathlib.Path) -> None:
    assert parse_opencode_storage(tmp_path / "nope") == []


def test_malformed_files_are_skipped(storage: pathlib.Path) -> None:
    (storage / "session" / "proj1" / "broken.json").write_text("{not json", encoding="utf-8")
    sessions = parse_opencode_storage(storage)
    # The good session is still returned; the broken file is skipped.
    assert [s.session_id for s in sessions] == ["sess1"]


def test_reader_dispatches_opencode_via_xdg(storage: pathlib.Path, tmp_path, monkeypatch) -> None:
    # opencode_storage_dir() honours XDG_DATA_HOME → tmp_path/opencode/storage.
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert opencode_storage_dir() == storage
    reader = FileTranscriptReader()
    sessions = reader.list_sessions(agent_type_value="opencode", config_dir="/ignored")
    assert [s.session_id for s in sessions] == ["sess1"]
    one = reader.read_session(
        agent_type_value="opencode", config_dir="/ignored", session_id="sess1"
    )
    assert one.project_path == "/work/myrepo"
    with pytest.raises(KeyError):
        reader.read_session(agent_type_value="opencode", config_dir="/ignored", session_id="nope")
