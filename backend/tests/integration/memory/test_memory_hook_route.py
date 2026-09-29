"""``POST /api/v1/memory/hook``, the trigger REST family and the Delivered
view, through the whole daemon on a fake home (spec memory "Retrieve the notes
a prompt names", "Guard a known trap once per session", "Keep triggers in the
vault, armed only by a person", "Show what each agent is given at session
start", "Audit every delivery fire").

Every test boots ``create_app`` (see ``_hook_app.boot``); the notes come from a
real ``memory sync`` padded with filler notes to the size the relevance floor
is calibrated for. The one test that needs a model — distil proposing a
trigger — gives the daemon's memory service a scripted completion that answers
the routing and writing stages by what they ask.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator
from typing import Any

import pytest
from typer.testing import CliRunner

from coffer.application.memory.distil_routing import ROUTING_SYSTEM
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http.memory.dependencies import get_memory_service
from tests.integration.memory._hook_app import (
    HookApp,
    audit,
    boot,
    distilled,
    extract_json,
    fire,
    partitions,
    register,
    seed_repository,
    sync,
    triggers_dir,
)

_runner = CliRunner()
_PROMPT = "why does make verify fail with undici AbortSignal under node"
_NOTE = "node-20-for-make-verify"


@pytest.fixture
def app(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[HookApp]:
    yield from boot(tmp_path, monkeypatch)


def _cli(*args: str) -> str:
    result = _runner.invoke(cli_app, list(args))
    assert result.exit_code == 0, result.output
    return str(result.output)


def _triggers(app: HookApp) -> list[dict[str, Any]]:
    r = app.client.get("/memory/triggers")
    assert r.status_code == 200, r.text
    return list(r.json()["triggers"])


def _files(app: HookApp) -> list[str]:
    d = triggers_dir(app)
    return sorted(p.name for p in d.glob("*.md")) if d.is_dir() else []


# --- each moment through the route ------------------------------------------------


@pytest.mark.acceptance(spec="memory", scenario="a prompt brings in the notes it names")
@pytest.mark.acceptance(
    spec="memory", scenario="a matching command is denied once with the note as the reason"
)
@pytest.mark.acceptance(
    spec="memory", scenario="a prompt and a guard fire each name their moment and notes"
)
def test_the_route_answers_every_moment_and_audits_what_it_delivered(app: HookApp) -> None:
    uid = register(app.client, "claude_code")
    repo, name = distilled(app)
    note_file = str(app.home / "memory" / name / "notes" / f"{_NOTE}.md")
    r = app.client.post(
        "/memory/triggers",
        json={"note": f"{name}/{_NOTE}", "command": r"^make\s+verify\b", "unless": "v20"},
    )
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    r = app.client.post(
        "/memory/triggers",
        json={"note": f"{name}/{_NOTE}", "kind": "context", "error": "AbortSignal"},
    )
    assert r.status_code == 201, r.text
    ctx_tid = r.json()["id"]
    base = {"cwd": str(repo), "session_id": "s1"}

    start = fire(app.client, uid, "SessionStart", **base)
    assert start is not None and start["hookSpecificOutput"]["hookEventName"] == "SessionStart"

    prompt = fire(app.client, uid, "UserPromptSubmit", prompt=_PROMPT, **base)
    assert prompt is not None
    text = prompt["hookSpecificOutput"]["additionalContext"]
    assert note_file in text
    assert len(text.encode("utf-8")) <= 1500
    assert 1 <= len(text.splitlines()) - 1 <= 3

    held = fire(app.client, uid, "PreToolUse", tool_name="Bash", command="make verify", **base)
    assert held is not None
    out = held["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert note_file in out["permissionDecisionReason"]
    assert "held once" in out["permissionDecisionReason"].lower()
    again = fire(app.client, uid, "PreToolUse", tool_name="Bash", command="make verify", **base)
    assert again is None
    fixed = "PATH=$HOME/.nvm/versions/node/v20.20.2/bin:$PATH make verify"
    fresh = {"cwd": str(repo), "session_id": "s2"}
    assert fire(app.client, uid, "PreToolUse", tool_name="Bash", command=fixed, **fresh) is None

    after = fire(
        app.client,
        uid,
        "PostToolUse",
        tool_name="Bash",
        command="make verify",
        output="TypeError: undici AbortSignal",
        **base,
    )
    assert after is not None
    assert "permissionDecision" not in after["hookSpecificOutput"]
    assert note_file in after["hookSpecificOutput"]["additionalContext"]

    fires = audit(app.client, "memory_delivery_fired")
    by_moment = {f["details"]["moment"]: f for f in fires}
    assert sorted(f["details"]["moment"] for f in fires) == [
        "error",
        "guard",
        "prompt",
        "session_start",
    ]
    for f in fires:
        assert f["actor"] == "claude-code" and f["resource_kind"] == "agent"
    assert f"{name}/{_NOTE}" in by_moment["prompt"]["details"]["notes"]
    assert by_moment["guard"]["details"]["trigger"] == tid
    assert by_moment["guard"]["details"]["notes"] == [f"{name}/{_NOTE}"]
    assert by_moment["error"]["details"]["trigger"] == ctx_tid
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


# --- triggers ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="memory", scenario="triggers are managed from REST and the command line"
)
def test_a_trigger_is_added_disarmed_armed_and_deleted_across_rest_and_cli(
    app: HookApp,
) -> None:
    assert _triggers(app) == []
    added = extract_json(
        _cli(
            "memory",
            "trigger",
            "add",
            "--note",
            "coffer/node-20",
            "--command",
            r"^make\s+verify\b",
            "--json",
        )
    )
    tid = added["id"]
    assert added["armed"] is True and added["armed_by"] == "user"
    path = triggers_dir(app) / f"{tid}.md"
    assert added["path"] == str(path)
    assert "armed_by: user" in path.read_text(encoding="utf-8")
    assert [t["armed"] for t in _triggers(app)] == [True]

    r = app.client.post(f"/memory/triggers/{tid}/disarm")
    assert r.status_code == 200, r.text
    assert [t["armed"] for t in _triggers(app)] == [False]
    assert "armed_by: user" not in path.read_text(encoding="utf-8")

    armed = _cli("memory", "trigger", "arm", tid)
    assert f"{tid}  armed  block  coffer/node-20" in armed
    assert [t["armed"] for t in _triggers(app)] == [True]
    assert "armed_by: user" in path.read_text(encoding="utf-8")
    listed = _cli("memory", "trigger", "list")
    assert tid in listed and "armed" in listed

    r = app.client.delete(f"/memory/triggers/{tid}")
    assert r.status_code == 204, r.text
    assert _triggers(app) == [] and not path.exists()
    assert "no memory triggers" in _cli("memory", "trigger", "list")

    for event in ("added", "disarmed", "armed", "deleted"):
        (entry,) = audit(app.client, f"memory_trigger_{event}")
        assert entry["actor"] == "user"
        assert entry["details"] == {"trigger": tid, "note": "coffer/node-20", "kind": "block"}

    r = app.client.post("/memory/triggers", json={"note": "coffer/x", "command": "(unclosed"})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "MEMORY_TRIGGER_INVALID"
    assert _files(app) == []
    r = app.client.post(f"/memory/triggers/{tid}/arm")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "MEMORY_TRIGGER_NOT_FOUND"


@pytest.mark.acceptance(spec="memory", scenario="a fresh vault has no triggers")
def test_a_fresh_vault_has_no_triggers_after_aggregating_and_distilling(app: HookApp) -> None:
    register(app.client, "claude_code")
    seed_repository(app)
    result = sync(app.client)
    assert result["entries_written"] == 2
    assert _triggers(app) == []
    assert _files(app) == []
    assert audit(app.client, "memory_trigger_proposed") == []


class _ProposingCompletion:
    """Routes every entry to a new note; writes each, proposing a trigger only
    for the note about the lockfile."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def complete(self, *, system: str, user: str, **_kw: Any) -> str:
        self.calls.append(system[:20])
        if system == ROUTING_SYSTEM:
            entries = json.loads(user)["entries"]
            return json.dumps(
                {
                    "actions": [
                        {"entry": e["id"], "action": "open", "title": e["title"]} for e in entries
                    ]
                }
            )
        is_lockfile = "uv sync" in user
        return json.dumps(
            {
                "title": "Python lockfile" if is_lockfile else "Worktree development",
                "description": "install with uv sync --frozen, never pip install"
                if is_lockfile
                else "always develop in a git worktree",
                "body": "Dependencies are locked with uv.\n",
                "trigger": {"command": r"^pip3?\s+install\b", "unless": ""}
                if is_lockfile
                else None,
            }
        )


class _Selector:
    async def get_default(self) -> Any:
        return "internal-connection"


@pytest.mark.acceptance(
    spec="memory", scenario="a proposed trigger does nothing until a person arms it"
)
def test_distils_proposal_lands_unarmed_and_holds_only_once_a_person_arms_it(
    app: HookApp,
) -> None:
    uid = register(app.client, "claude_code")
    service = get_memory_service()
    completion = _ProposingCompletion()
    service._completion = completion  # type: ignore[assignment]
    service._models = _Selector()  # type: ignore[assignment]
    service._credential_resolver = lambda _ref: "key"
    repo = seed_repository(app)
    sync(app.client)
    assert completion.calls, "the distil pass must have used the scripted model"

    (trigger,) = _triggers(app)
    assert trigger["proposed_by"] == "distil"
    assert trigger["armed"] is False and trigger["armed_by"] == ""
    assert trigger["note"].startswith("coffer/")
    assert _files(app) == [f"{trigger['id']}.md"]
    text = (triggers_dir(app) / f"{trigger['id']}.md").read_text(encoding="utf-8")
    assert "proposed_by: distil" in text and "armed_by: distil" not in text
    (proposed,) = audit(app.client, "memory_trigger_proposed")
    assert proposed["actor"] == "distil"
    assert proposed["details"]["trigger"] == trigger["id"]

    cmd = {"tool_name": "Bash", "command": "pip install requests", "cwd": str(repo)}
    assert fire(app.client, uid, "PreToolUse", session_id="s1", **cmd) is None

    assert "armed" in _cli("memory", "trigger", "arm", trigger["id"])
    held = fire(app.client, uid, "PreToolUse", session_id="s2", **cmd)
    assert held is not None
    out = held["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    note_path = app.home / "memory" / trigger["note"].replace("/", "/notes/", 1)
    assert str(note_path) + ".md" in out["permissionDecisionReason"]
