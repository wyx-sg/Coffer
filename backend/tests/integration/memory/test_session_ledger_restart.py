"""A daemon restart keeps what each session was given (spec memory "Remember
what a session was given across daemon restarts").

Two daemon lifetimes over one fake home and database (``_hook_app.boot``): the
first delivers a note at a prompt; the second, started fresh, is asked the
same thing in the same session and gives nothing again, while a new session still gets both.
"""

from __future__ import annotations

import pathlib

import pytest

from tests.integration.memory._hook_app import boot, distilled, fire, register

_PROMPT = "why does make verify fail with undici AbortSignal under node"
_NOTE = "node-20-for-make-verify"


@pytest.mark.acceptance(spec="memory", scenario="a daemon restart gives a session nothing twice")
def test_a_daemon_restart_gives_a_session_nothing_twice(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = boot(tmp_path, monkeypatch)
    app = next(first)
    uid = register(app.client, "claude_code")
    repo, _name = distilled(app)
    same = {"cwd": str(repo), "session_id": "s1"}
    assert fire(app.client, uid, "UserPromptSubmit", prompt=_PROMPT, **same) is not None
    first.close()

    second = boot(tmp_path, monkeypatch)
    app = next(second)
    try:
        assert fire(app.client, uid, "UserPromptSubmit", prompt=_PROMPT, **same) is None
        fresh = {"cwd": str(repo), "session_id": "s2"}
        out = fire(app.client, uid, "UserPromptSubmit", prompt=_PROMPT, **fresh)
        assert out is not None
        assert _NOTE in out["hookSpecificOutput"]["additionalContext"]
    finally:
        second.close()
