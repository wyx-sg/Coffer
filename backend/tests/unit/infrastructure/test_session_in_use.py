"""Is a session open outside the daemon? Decided from a process list.

Spec chat "Run a session in one place at a time". The process list is a fake;
the daemon's own tree (the Agent SDK's ``claude --resume``) never counts.
"""

from __future__ import annotations

import pytest

from coffer.infrastructure.chat.session_in_use import ProcessInfo, ProcessSessionInUse

SID = "550e8400-e29b-41d4-a716-446655440000"
DAEMON = 100


def _port(*processes: ProcessInfo) -> ProcessSessionInUse:
    return ProcessSessionInUse(processes=lambda: list(processes), own_pid=lambda: DAEMON)


def _proc(pid: int, ppid: int, *argv: str) -> ProcessInfo:
    return ProcessInfo(pid, ppid, argv)


@pytest.mark.acceptance(
    spec="chat", scenario="a session open in a terminal refuses the channel turn"
)
async def test_a_terminal_process_naming_the_session_counts() -> None:
    claude = _port(_proc(1, 0, "launchd"), _proc(500, 1, "claude", "--resume", SID))
    codex = _port(_proc(501, 1, "codex", "resume", SID))
    equals_form = _port(_proc(502, 1, "claude", f"--resume={SID}"))

    assert await claude.in_use(SID)
    assert await codex.in_use(SID)
    assert await equals_form.in_use(SID)


@pytest.mark.acceptance(spec="chat", scenario="the daemon's own turn does not count")
async def test_the_daemons_own_process_tree_never_counts() -> None:
    port = _port(
        _proc(DAEMON, 1, "coffer-daemon"),
        _proc(101, DAEMON, "claude", "--resume", SID),  # the Agent SDK's child
        _proc(102, 101, "node", "--resume", SID),  # and its child
    )

    assert not await port.in_use(SID)


async def test_a_terminal_beside_the_daemons_tree_still_counts() -> None:
    port = _port(
        _proc(DAEMON, 1, "coffer-daemon"),
        _proc(101, DAEMON, "claude", "--resume", SID),
        _proc(500, 1, "claude", "--resume", SID),
    )

    assert await port.in_use(SID)


@pytest.mark.acceptance(spec="chat", scenario="a session whose terminal closed runs again")
async def test_a_session_nobody_names_is_free() -> None:
    other = "another-session"
    port = _port(
        _proc(500, 1, "claude", "--resume", other),
        _proc(501, 1, "vim", f"notes-{SID}.txt"),  # part of an argument is not the id
        _proc(502, 1, "sh", "-lc", f"claude --resume {SID}"),  # one opaque argument
    )

    assert not await port.in_use(SID)
    assert not await _port().in_use(SID)
