"""A session open in a terminal is taken over by ending that terminal's process.

Spec chat "Take over a session open elsewhere". The process list and the ending
are fakes; the daemon's own tree (the Agent SDK's ``claude --resume``) is never
touched.
"""

from __future__ import annotations

import pytest

from coffer.infrastructure.chat.session_takeover import ProcessInfo, ProcessSessionTakeover

SID = "550e8400-e29b-41d4-a716-446655440000"
DAEMON = 100


class _Ender:
    def __init__(self, survivors: tuple[int, ...] = ()) -> None:
        self.ended: list[int] = []
        self._survivors = survivors

    def __call__(self, pids: list[int]) -> list[int]:
        self.ended.extend(pids)
        return [p for p in pids if p in self._survivors]


def _port(*processes: ProcessInfo, end: _Ender) -> ProcessSessionTakeover:
    return ProcessSessionTakeover(
        processes=lambda: list(processes), own_pid=lambda: DAEMON, end=end
    )


def _proc(pid: int, ppid: int, *argv: str) -> ProcessInfo:
    return ProcessInfo(pid, ppid, argv)


@pytest.mark.acceptance(spec="chat", scenario="a session open in a terminal is taken over")
async def test_a_terminal_process_naming_the_session_is_ended() -> None:
    end = _Ender()
    port = _port(
        _proc(1, 0, "launchd"),
        _proc(500, 1, "claude", "--resume", SID),
        _proc(501, 1, "codex", "resume", SID),
        _proc(502, 1, "claude", f"--resume={SID}"),
        end=end,
    )

    assert await port.release(SID)
    assert end.ended == [500, 501, 502]


@pytest.mark.acceptance(spec="chat", scenario="the daemon's own turn is never ended")
async def test_the_daemons_own_process_tree_is_never_ended() -> None:
    end = _Ender()
    port = _port(
        _proc(DAEMON, 1, "coffer-daemon"),
        _proc(101, DAEMON, "claude", "--resume", SID),  # the Agent SDK's child
        _proc(102, 101, "node", "--resume", SID),  # and its child
        end=end,
    )

    assert await port.release(SID)
    assert end.ended == []


async def test_a_terminal_beside_the_daemons_tree_is_still_ended() -> None:
    end = _Ender()
    port = _port(
        _proc(DAEMON, 1, "coffer-daemon"),
        _proc(101, DAEMON, "claude", "--resume", SID),
        _proc(500, 1, "claude", "--resume", SID),
        end=end,
    )

    assert await port.release(SID)
    assert end.ended == [500]


async def test_a_process_that_will_not_end_keeps_the_session() -> None:
    end = _Ender(survivors=(500,))
    port = _port(_proc(500, 1, "claude", "--resume", SID), end=end)

    assert not await port.release(SID)


async def test_a_session_nobody_names_is_free_and_nothing_is_ended() -> None:
    end = _Ender()
    port = _port(
        _proc(500, 1, "claude", "--resume", "another-session"),
        _proc(501, 1, "vim", f"notes-{SID}.txt"),  # part of an argument is not the id
        _proc(502, 1, "sh", "-lc", f"claude --resume {SID}"),  # one opaque argument
        end=end,
    )

    assert await port.release(SID)
    assert end.ended == []
