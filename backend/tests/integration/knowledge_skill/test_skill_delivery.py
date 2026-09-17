"""The knowledge layer's delivery half, through the real composition root.

An agent only reads this layer if it knows the layer is there — and with no
retrieval tool left (spec knowledge FR-033), the delivered skill IS the
interface. What the unit tests beside ``application/knowledge`` cannot show is
that the daemon actually wires and runs delivery: the skill is written on every
boot (``surfaces/http/app.py``), into the directory the *agent* Resource names,
which is a bridge between two kinds only the composition root may cross.

This module is deliberately not the old one. The knowledge skill used to be a
skill-manager Resource seeded into ``~/.coffer/skills/`` and symlinked per
agent; it is now rendered per agent and written as real bytes (FR-051, FR-052),
so the seed-and-symlink assertions had nothing left to assert.
"""

from __future__ import annotations

import pathlib

import pytest
from starlette.testclient import TestClient

from coffer.application.knowledge.skill_render import SKILL_NAME
from coffer.surfaces.http.auth import set_active_token

_TOKEN = "test-token-knowledge-skill-delivery"
_HEADERS = {"X-Coffer-Token": _TOKEN}


@pytest.fixture
def home(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59660")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59669")
    return tmp_path


def _client() -> TestClient:
    from coffer.surfaces.http.app import create_app

    app = create_app()
    set_active_token(_TOKEN)
    return TestClient(app, headers=_HEADERS)


def _register_agent(client: TestClient, name: str, config_dir: pathlib.Path) -> None:
    resp = client.post(
        "/api/v1/agents",
        json={"type": "claude_code", "name": name, "config_dir": str(config_dir)},
    )
    assert resp.status_code == 201, resp.text


def _seed_collection(client: TestClient, name: str, description: str) -> None:
    resp = client.post(
        "/api/v1/knowledge/collections", json={"name": name, "description": description}
    )
    assert resp.status_code == 201, resp.text


def test_the_skill_is_written_into_the_agents_own_directory_on_boot(home) -> None:  # type: ignore[no-untyped-def]
    """Real bytes at ``<config_dir>/skills/coffer-knowledge/SKILL.md``.

    The delivery happens during startup, so the agent is registered against one
    daemon and the assertion is made after a second one has booted over the
    same HOME — which is also the path that heals a copy a person deleted.
    """
    config_dir = home / "agent-cfg"
    config_dir.mkdir()

    with _client() as client:
        _seed_collection(client, "shopee", "Shopee's account system and the platforms around it.")
        _register_agent(client, "delivered-to", config_dir)

    with _client():
        pass

    skill = config_dir / "skills" / SKILL_NAME / "SKILL.md"
    assert skill.is_file(), (
        "the knowledge skill never reached the agent's own skill directory: "
        f"{sorted(p.name for p in (config_dir / 'skills').glob('*'))}"
    )
    # Real bytes, not a link into a shared master — that is what lets two
    # agents hold different catalogues (FR-052).
    assert not skill.is_symlink()
    assert not skill.parent.is_symlink()

    text = skill.read_text(encoding="utf-8")
    assert f"name: {SKILL_NAME}" in text
    # The description carries the collection's own subject (FR-053) and the
    # body carries the absolute root the agent reads at (FR-054).
    assert "Shopee's account system" in text
    assert str(home / "knowledge") in text
    # And it names the one tool that is left, never a retrieval tool (FR-050).
    assert "coffer__write" in text
    for gone in ("coffer__read", "coffer__list", "coffer__grep", "coffer__search"):
        assert gone not in text, gone


def test_the_knowledge_skill_is_not_a_managed_skill_resource(home) -> None:  # type: ignore[no-untyped-def]
    """FR-051: it is a file this layer owns, not a Resource skill-manager
    delivers. A vault that still registered it would deliver it twice — once
    as the generated per-agent copy and once as a shared master symlink that
    silently overwrote it."""
    with _client() as client:
        listed = client.get("/api/v1/skills")
        assert listed.status_code == 200, listed.text
        assert SKILL_NAME not in {s["name"] for s in listed.json()["items"]}

    assert not (home / ".coffer" / "skills" / SKILL_NAME).exists()


def test_a_second_boot_rewrites_rather_than_duplicates(home) -> None:  # type: ignore[no-untyped-def]
    """Delivery is idempotent: it heals an edited copy instead of stacking
    another one beside it."""
    config_dir = home / "agent-cfg"
    config_dir.mkdir()

    with _client() as client:
        _seed_collection(client, "shopee", "Internal systems.")
        _register_agent(client, "delivered-to", config_dir)

    skill = config_dir / "skills" / SKILL_NAME / "SKILL.md"
    with _client():
        pass
    original = skill.read_text(encoding="utf-8")

    skill.write_text("someone edited this\n", encoding="utf-8")
    with _client():
        pass

    assert skill.read_text(encoding="utf-8") == original
    assert sorted(p.name for p in (config_dir / "skills").iterdir()) == [SKILL_NAME]
