"""``ClaudeNativeSessions`` lists and changes sessions through the Agent SDK.

The SDK's three functions are replaced with fakes (``monkeypatch``); the tests
cover the title rule, search, ordering, the keyset position, the
``CLAUDE_CONFIG_DIR`` handling and the error mapping.
"""

from __future__ import annotations

import os
import pathlib
from types import SimpleNamespace
from typing import Any

import claude_agent_sdk
import pytest

from coffer.domain.agent.native_sessions import NativeSessionInvalid, NativeSessionNotFound
from coffer.domain.pagination import CursorInvalid, position_of
from coffer.infrastructure.agent.claude_native_sessions import ClaudeNativeSessions


def _info(session_id: str, ms: int, **extra: Any) -> SimpleNamespace:
    fields: dict[str, Any] = {
        "session_id": session_id,
        "summary": f"summary {session_id}",
        "last_modified": ms,
        "custom_title": None,
        "first_prompt": None,
        "cwd": "/work/repo",
        "created_at": ms - 1000,
    }
    fields.update(extra)
    return SimpleNamespace(**fields)


@pytest.fixture
def home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    return tmp_path


def _fake_list(monkeypatch: pytest.MonkeyPatch, infos: list[Any]) -> list[str | None]:
    seen: list[str | None] = []

    def fake() -> list[Any]:
        seen.append(os.environ.get("CLAUDE_CONFIG_DIR"))
        return list(infos)

    monkeypatch.setattr(claude_agent_sdk, "list_sessions", fake)
    return seen


async def test_sessions_are_titled_scrubbed_searched_and_ordered(
    home: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_list(
        monkeypatch,
        [
            _info("a", 3000, custom_title="Auth work", summary="auto"),
            _info("b", 2000, summary="", first_prompt="deploy sk-abcdefghijklmnopqrstuvwx"),
            _info("c", 2000, summary="Billing", cwd="/srv/Auth-service"),
            _info("d", 1000, summary="Other", cwd=None),
        ],
    )
    source = ClaudeNativeSessions()

    everything = await source.list(home / ".claude", q=None, limit=10, position=None)
    # Newest first; equal times break by session id.
    assert [s.session_id for s in everything.items] == ["a", "c", "b", "d"]
    assert [s.title for s in everything.items] == [
        "Auth work",
        "Billing",
        "deploy [redacted]",
        "Other",
    ]
    assert everything.total == 4 and everything.next_position is None
    assert everything.items[0].last_activity_at is not None
    assert everything.items[0].created_at is not None

    # Case-insensitive, over the title and the working directory.
    found = await source.list(home / ".claude", q="AUTH", limit=10, position=None)
    assert [s.session_id for s in found.items] == ["a", "c"]
    assert found.total == 2


@pytest.mark.acceptance(
    spec="agent-registry/claude-code",
    scenario="a new Claude Code session does not shift the next page",
)
async def test_a_session_written_between_two_reads_does_not_shift_the_next_page(
    home: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    infos = [_info(str(i), 1000 + i) for i in range(5)]
    _fake_list(monkeypatch, infos)
    source = ClaudeNativeSessions()

    first = await source.list(home / ".claude", q=None, limit=2, position=None)
    # A session is written (the newest of all) before the next page is read.
    infos.append(_info("new", 9000))
    second = await source.list(home / ".claude", q=None, limit=2, position=first.next_position)
    third = await source.list(home / ".claude", q=None, limit=2, position=second.next_position)

    assert [s.session_id for s in first.items] == ["4", "3"]
    assert [s.session_id for s in second.items] == ["2", "1"]
    assert [s.session_id for s in third.items] == ["0"]
    assert third.next_position is None
    # The position names the last row (its activity time and id), not an offset.
    assert first.next_position is not None and first.next_position[1] == "3"
    assert "new" not in {s.session_id for s in first.items + second.items + third.items}


async def test_a_position_that_does_not_fit_is_refused(
    home: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_list(monkeypatch, [_info("a", 1000)])
    source = ClaudeNativeSessions()

    for bad in (["not-a-time", "a"], [5], ["2026-01-01T00:00:00+00:00", 7]):
        with pytest.raises(CursorInvalid):
            await source.list(home / ".claude", q=None, limit=2, position=bad)


async def test_equal_activity_times_page_by_session_id(
    home: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_list(monkeypatch, [_info(name, 2000) for name in ("a", "b", "c")])
    source = ClaudeNativeSessions()

    first = await source.list(home / ".claude", q=None, limit=2, position=None)
    second = await source.list(home / ".claude", q=None, limit=2, position=first.next_position)

    assert [s.session_id for s in first.items] == ["c", "b"]
    assert [s.session_id for s in second.items] == ["a"]
    assert first.next_position == position_of(first.items[-1].last_activity_at, "b")


@pytest.mark.acceptance(
    spec="agent-registry/claude-code", scenario="list sessions of a custom config directory"
)
async def test_a_custom_config_dir_is_set_around_the_call_and_restored(
    home: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _fake_list(monkeypatch, [])
    custom = home / "work-claude"
    source = ClaudeNativeSessions()

    await source.list(custom, q=None, limit=5, position=None)
    await source.list(home / ".claude", q=None, limit=5, position=None)

    assert seen == [str(custom), None]
    assert "CLAUDE_CONFIG_DIR" not in os.environ


async def test_an_existing_variable_is_restored_after_the_call(
    home: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/previous")
    seen = _fake_list(monkeypatch, [])

    await ClaudeNativeSessions().list(home / "other", q=None, limit=5, position=None)

    assert seen == [str(home / "other")]
    assert os.environ["CLAUDE_CONFIG_DIR"] == "/previous"


@pytest.mark.acceptance(
    spec="agent-registry/claude-code", scenario="rename and delete go through the SDK"
)
async def test_rename_and_delete_call_the_sdk_and_map_its_errors(
    home: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, tuple[str, ...], str | None]] = []

    def rename(session_id: str, title: str) -> None:
        calls.append(("rename", (session_id, title), os.environ.get("CLAUDE_CONFIG_DIR")))
        if session_id == "bad":
            raise ValueError("Invalid session_id: bad")

    def delete(session_id: str) -> None:
        calls.append(("delete", (session_id,), os.environ.get("CLAUDE_CONFIG_DIR")))
        raise FileNotFoundError(session_id)

    monkeypatch.setattr(claude_agent_sdk, "rename_session", rename)
    monkeypatch.setattr(claude_agent_sdk, "delete_session", delete)
    source = ClaudeNativeSessions()
    custom = home / "work-claude"

    await source.rename(custom, "s1", "New")
    with pytest.raises(NativeSessionInvalid):
        await source.rename(custom, "bad", "New")
    with pytest.raises(NativeSessionNotFound):
        await source.delete(home / ".claude", "s2")

    assert calls[0] == ("rename", ("s1", "New"), str(custom))
    assert calls[2] == ("delete", ("s2",), None)
