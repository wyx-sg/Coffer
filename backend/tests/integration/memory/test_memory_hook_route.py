"""``POST /api/v1/memory/hook`` and the Delivered view, through the whole
daemon on a fake home (spec memory "Retrieve the notes a prompt names", "Show
what each agent is given at session start", "Audit every delivery fire").

Every test boots ``create_app`` (see ``_hook_app.boot``); the notes come from a
real ``memory sync`` padded with filler notes to the size the relevance floor
is calibrated for.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator

import pytest

from tests.integration.memory._hook_app import (
    HookApp,
    audit,
    boot,
    distilled,
    fire,
    partitions,
    register,
)

_PROMPT = "why does make verify fail with undici AbortSignal under node"
_NOTE = "node-20-for-make-verify"


@pytest.fixture
def app(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[HookApp]:
    yield from boot(tmp_path, monkeypatch)


# --- each moment through the route ------------------------------------------------


@pytest.mark.acceptance(spec="memory", scenario="a prompt brings in the notes it names")
@pytest.mark.acceptance(spec="memory", scenario="every hook fire is recorded in the audit log")
@pytest.mark.acceptance(
    spec="memory",
    scenario="name the moment and the notes of a session-start fire and a prompt fire",
)
def test_the_route_answers_both_moments_and_audits_what_it_delivered(app: HookApp) -> None:
    uid = register(app.client, "claude_code")
    repo, name = distilled(app)
    note_file = str(app.home / ".coffer" / "derived" / "memory" / name / "notes" / f"{_NOTE}.md")
    base = {"cwd": str(repo), "session_id": "s1"}

    start = fire(app.client, uid, "SessionStart", **base)
    assert start is not None and start["hookSpecificOutput"]["hookEventName"] == "SessionStart"

    prompt = fire(app.client, uid, "UserPromptSubmit", prompt=_PROMPT, **base)
    assert prompt is not None
    text = prompt["hookSpecificOutput"]["additionalContext"]
    assert note_file in text
    assert len(text.encode("utf-8")) <= 1500
    assert 1 <= len(text.splitlines()) - 1 <= 3

    # The shell-tool moments are not Coffer's: an entry an earlier build left
    # there answers nothing, and denies nothing.
    for event in ("PreToolUse", "PostToolUse"):
        assert fire(app.client, uid, event, **base) is None

    fires = audit(app.client, "memory_delivery_fired")
    by_moment = {f["details"]["moment"]: f for f in fires}
    assert sorted(by_moment) == ["prompt", "session_start"] and len(fires) == 2
    for f in fires:
        assert f["actor"] == "claude-code" and f["resource_kind"] == "agent"
    assert f"{name}/{_NOTE}" in by_moment["prompt"]["details"]["notes"]
    dumped = json.dumps(fires)
    assert "undici AbortSignal under Node 22" not in dumped
    assert "standing rule" not in dumped


@pytest.mark.acceptance(spec="memory", scenario="a short or trivial prompt retrieves nothing")
def test_a_trivial_prompt_or_an_unknown_event_answers_null_and_audits_nothing(
    app: HookApp,
) -> None:
    uid = register(app.client, "claude_code")
    repo, _name = distilled(app)
    for prompt in ("继续", "ok", "make verify"):
        assert fire(app.client, uid, "UserPromptSubmit", prompt=prompt, cwd=str(repo)) is None
    assert fire(app.client, uid, "Stop", cwd=str(repo), session_id="s") is None
    assert audit(app.client, "memory_delivery_fired") == []


# --- the Delivered view ---------------------------------------------------------------


@pytest.mark.acceptance(
    spec="memory", scenario="the Delivered view carries each agent's exact session-start text"
)
def test_the_delivered_view_is_the_session_start_answer_for_each_agent(app: HookApp) -> None:
    cc = register(app.client, "claude_code")
    cx = register(app.client, "codex")
    repo, name = distilled(app)
    uid = partitions(app.client)[name]["uid"]
    before = len(app.client.get("/audit", params={"limit": 500}).json()["entries"])

    r = app.client.get(f"/memory/partitions/{uid}/delivered")
    assert r.status_code == 200, r.text
    body = r.json()
    after = len(app.client.get("/audit", params={"limit": 500}).json()["entries"])
    assert after == before  # reading the view audits nothing

    assert body["partition"] == name
    entries = {a["agent_uid"]: a for a in body["agents"]}
    assert set(entries) == {cc, cx}
    for agent_uid, entry in entries.items():
        assert entry["event"] == "SessionStart"
        assert set(entry) == {"agent_uid", "agent_name", "agent_type", "event", "text"}
        answer = fire(app.client, agent_uid, "SessionStart", cwd=str(repo), session_id="x")
        assert answer is not None
        assert entry["text"] == answer["hookSpecificOutput"]["additionalContext"]
        assert entry["text"]
