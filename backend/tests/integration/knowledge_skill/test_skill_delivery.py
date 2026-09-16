"""The knowledge layer's delivery half.

An agent only reads this layer if it knows the layer is there. The audit behind
the redesign found a tool's own description does not achieve that — every
knowledge call in a month's history came from the session that built the corpus.
A skill does: Coffer already delivers skills into each managed agent's own
directory, and a skill's name and description sit in the agent's context
(spec knowledge FR-042).
"""

from __future__ import annotations

import pathlib

import pytest
from starlette.testclient import TestClient

from coffer.application.knowledge.skill_seed import SKILL_NAME
from coffer.surfaces.http.auth import set_active_token

_TOKEN = "test-token-knowledge-skill-delivery"


def _app(tmp_path, monkeypatch, *, port_start: int):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    from coffer.surfaces.http.app import create_app

    app = create_app()
    set_active_token(_TOKEN)
    return app


@pytest.mark.acceptance(
    spec="knowledge", scenario="the knowledge skill is delivered to a managed agent"
)
def test_the_knowledge_skill_is_delivered_to_a_managed_agent(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """FR-042 end to end: seeded into master, then DELIVERED to an agent.

    This used to boot the app and assert only that the file existed under
    ``~/.coffer/skills/`` — Coffer's master store. That is seeding. No agent
    was registered, no binding existed, and no agent-side directory was looked
    at, so the scenario's own promise ("present in **its** skill directory")
    was never exercised and the delivery path could have been broken outright
    without this going red.

    So an agent is registered here and the assertion moved onto the agent's
    own ``<config_dir>/skills/``, reached through the real path
    (``apply_scope_for_agent`` runs on registration and delivers every enabled,
    in-scope skill). The skill is read back THROUGH the agent's directory, not
    from master, so the agent-side link being dangling is a failure too.
    """
    app = _app(tmp_path, monkeypatch, port_start=59660)
    agent_config_dir = tmp_path / "agent-cfg"
    agent_config_dir.mkdir()

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        # Seeding happens during the daemon's own startup, before any agent
        # exists — so master holds the skill and no agent does yet.
        master = pathlib.Path(tmp_path) / ".coffer" / "skills" / SKILL_NAME / "SKILL.md"
        assert master.is_file(), "the knowledge skill was not seeded into the master store"
        assert not (agent_config_dir / "skills" / SKILL_NAME).exists()

        resp = client.post(
            "/api/v1/agents",
            json={
                "type": "claude_code",
                "name": "delivered-to",
                "config_dir": str(agent_config_dir),
            },
        )
        assert resp.status_code == 201, resp.text

        # The binding Coffer recorded, and the agent-side copy it made.
        skill = client.get(f"/api/v1/skills/{SKILL_NAME}")
        assert skill.status_code == 200, skill.text
        assert [b["agent_name"] for b in skill.json()["bindings"]] == ["delivered-to"]

    delivered = agent_config_dir / "skills" / SKILL_NAME / "SKILL.md"
    assert delivered.is_file(), (
        f"the knowledge skill never reached the agent's own skill directory: "
        f"{sorted(p.name for p in (agent_config_dir / 'skills').glob('*'))}"
    )

    text = delivered.read_text(encoding="utf-8")
    assert f"name: {SKILL_NAME}" in text
    # The body has to teach catalogue-then-grep, not just announce the tools:
    # descending one level at a time is what keeps a large corpus readable.
    # `coffer__search` is in this list because FR-042 requires the skill to
    # teach "when to reach for `search` instead" — it was the one tool the
    # loop omitted, which is how the delivered skill could have stopped
    # mentioning the file-at-a-time half without anything noticing.
    for tool in (
        "coffer__list",
        "coffer__read",
        "coffer__grep",
        "coffer__search",
        "coffer__write",
    ):
        assert tool in text, f"{tool} is not named in the skill body"
    # FR-024 + User Story 8: the delivered skill is one of the two places the
    # literal-matching caveat must be stated, because an agent that phrases a
    # question in its own words gets nothing back and no error to explain why.
    # Matched against whitespace-collapsed prose: the asset is hard-wrapped, so
    # a phrase can straddle a newline and a raw `in` would be asserting the
    # line breaks rather than the sentence.
    prose = " ".join(text.split())
    assert "never a question in your own words" in prose, (
        "the skill does not tell the agent to give search a word or exact "
        "phrase rather than a question in its own words"
    )
    assert "ranks by meaning" in prose, (
        "the skill does not say that nothing in the layer ranks by meaning"
    )


def test_seeding_again_is_a_no_op(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """It re-imports on every boot, so an edited asset ships with the next
    daemon start and a deleted skill comes back."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    from coffer.surfaces.http.app import create_app

    for _ in range(2):
        with TestClient(create_app()):
            pass

    installed = pathlib.Path(tmp_path) / ".coffer" / "skills" / SKILL_NAME / "SKILL.md"
    assert installed.is_file()
