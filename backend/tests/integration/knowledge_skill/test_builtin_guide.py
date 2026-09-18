"""Coffer's own skill, through the real composition root.

An agent only uses Coffer well if something tells it how, and with the
handshake instructions capped at 800 characters the skill IS that something.
What the unit tests beside ``application/knowledge`` and ``application/skill``
cannot show is that the daemon actually wires the two halves together and runs
them: the text comes from the knowledge layer, the master folder and the
resource row come from the skill layer, and those two kinds may not import each
other — the join exists only in the composition root, so only a booted app
proves it holds.

This module replaces the one that asserted the opposite contract. The knowledge
skill used to be written per agent as real bytes by a writer of its own, on the
grounds that a shared master was a copy nothing would re-render. It is an
ordinary skill resource again, because something does re-render it now: this
seed, at every boot and after every curation pass.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from starlette.testclient import TestClient

from coffer.application.knowledge.guide_render import GUIDE_SKILL_NAME
from coffer.surfaces.http.auth import set_active_token

_TOKEN = "test-token-builtin-guide"
_HEADERS = {"X-Coffer-Token": _TOKEN}

#: What the retired delivery left in every agent's skills directory.
_RETIRED = "coffer-knowledge"

_ALEMBIC_INI = (
    pathlib.Path(__file__).resolve().parents[3]
    / "coffer"
    / "infrastructure"
    / "persistence"
    / "migrations"
    / "alembic.ini"
)


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


def _master(home: pathlib.Path) -> pathlib.Path:
    return home / ".coffer" / "skills" / GUIDE_SKILL_NAME / "SKILL.md"


@pytest.mark.acceptance(
    spec="knowledge", scenario="Coffer's own skill is an ordinary skill resource"
)
def test_the_guide_is_seeded_as_an_ordinary_skill_resource(home) -> None:  # type: ignore[no-untyped-def]
    """One master folder, one row, and the row says Coffer wrote it.

    The seed runs during startup, so the collection and the agent are created
    against one daemon and the assertions are made after a second has booted
    over the same HOME.
    """
    config_dir = home / "agent-cfg"
    config_dir.mkdir()

    with _client() as client:
        _seed_collection(client, "shopee", "Shopee's account system and the platforms around it.")
        _register_agent(client, "delivered-to", config_dir)

    with _client() as client:
        listed = client.get("/api/v1/skills")
        assert listed.status_code == 200, listed.text
        rows = {s["name"]: s for s in listed.json()["items"]}
        assert GUIDE_SKILL_NAME in rows, sorted(rows)
        row = rows[GUIDE_SKILL_NAME]
        assert row["source"] == {"type": "builtin"}
        # Nothing about where it came from, because nothing about that would
        # still be true tomorrow — and the config converges to other machines.
        assert row["last_synced_from_source_at"] is None

    assert _master(home).is_file()


@pytest.mark.acceptance(
    spec="knowledge", scenario="every agent reaches the guide through the one master folder"
)
def test_the_agent_holds_a_link_into_the_master(home) -> None:  # type: ignore[no-untyped-def]
    """Delivered by the same links as any other skill, not copied per agent.

    That is the whole point of it being a resource: one folder to re-render,
    and every agent's copy follows in the same instant.
    """
    config_dir = home / "agent-cfg"
    config_dir.mkdir()

    with _client() as client:
        _seed_collection(client, "shopee", "Internal systems.")
        _register_agent(client, "delivered-to", config_dir)
    with _client():
        pass

    delivered = config_dir / "skills" / GUIDE_SKILL_NAME
    assert delivered.is_symlink(), sorted(p.name for p in (config_dir / "skills").glob("*"))
    assert delivered.resolve() == _master(home).parent.resolve()
    assert (delivered / "SKILL.md").read_text(encoding="utf-8") == _master(home).read_text(
        encoding="utf-8"
    )


@pytest.mark.acceptance(
    spec="knowledge", scenario="the skill body carries the catalogue and the absolute root"
)
def test_the_guide_carries_the_manual_and_the_catalogue(home) -> None:  # type: ignore[no-untyped-def]
    """Both halves in one file: what Coffer does, and what it currently holds."""
    with _client() as client:
        _seed_collection(client, "shopee", "Shopee's account system and the platforms around it.")
    with _client():
        pass

    text = _master(home).read_text(encoding="utf-8")
    assert f"name: {GUIDE_SKILL_NAME}" in text
    # The description is the only part always resident, so it carries the
    # collection's own subject — the thing a model can match on.
    assert "Shopee's account system" in text
    # The manual half.
    assert "coffer__search_tools" in text
    assert "never writes it" in text
    # The catalogue half, at the root this machine actually reads from.
    assert str(home / "knowledge") in text
    # And no tool that does not exist. Retrieval tools were removed from this
    # layer; a manual that still named one would have a model calling it.
    for gone in ("coffer__read", "coffer__list", "coffer__grep", "coffer__search\n"):
        assert gone not in text, gone


@pytest.mark.acceptance(
    spec="skill-manager", scenario="deleting Coffer's own skill is refused on every surface"
)
@pytest.mark.acceptance(
    spec="resource-framework", scenario="a kind refuses a deletion before anything is torn down"
)
def test_deleting_the_guide_is_refused_on_both_delete_routes(home) -> None:  # type: ignore[no-untyped-def]
    """It would come back at the next boot, so the delete is a no-op dressed
    as a destructive action. Both surfaces refuse it, because the guard is on
    the kind rather than on either route."""
    with _client():
        pass

    with _client() as client:
        for url in (
            f"/api/v1/skills/{GUIDE_SKILL_NAME}",
            f"/api/v1/resources/skill/{GUIDE_SKILL_NAME}",
        ):
            resp = client.delete(url)
            assert resp.status_code == 409, f"{url}: {resp.status_code} {resp.text}"
            assert resp.json()["error"]["code"] == "RESOURCE_PROTECTED", resp.text

    # Refused before anything was torn down: the master is untouched.
    assert _master(home).is_file()
    with _client() as client:
        assert client.get(f"/api/v1/skills/{GUIDE_SKILL_NAME}").status_code == 200


def test_disabling_the_guide_is_allowed_and_reclaims_the_copy(home) -> None:  # type: ignore[no-untyped-def]
    """Existence is Coffer's; reach is the owner's. Disabling still works."""
    config_dir = home / "agent-cfg"
    config_dir.mkdir()

    with _client() as client:
        _register_agent(client, "delivered-to", config_dir)
    with _client():
        pass
    assert (config_dir / "skills" / GUIDE_SKILL_NAME).is_symlink()

    with _client() as client:
        resp = client.post(f"/api/v1/resources/skill/{GUIDE_SKILL_NAME}/disable")
        assert resp.status_code == 200, resp.text

    delivered = config_dir / "skills" / GUIDE_SKILL_NAME
    assert not delivered.exists() and not delivered.is_symlink()
    # And the master survives, ready for the next enable.
    assert _master(home).is_file()


@pytest.mark.acceptance(
    spec="knowledge", scenario="a disabled collection is absent from every agent's skill"
)
def test_disabling_a_collection_rewrites_the_guide_at_once(home) -> None:  # type: ignore[no-untyped-def]
    """``enabled`` is this kind's only switch, and it has to reach the file.

    The catalogue lives in a rendered skill, so switching a collection off
    changes nothing an agent can see until that file is rewritten. Waiting for
    the next boot would leave the agent reading a catalogue its owner had
    already changed — and one master serves every agent, so it changes for all
    of them at once.
    """
    with _client() as client:
        _seed_collection(client, "shopee", "Shopee's account system.")
        _seed_collection(client, "personal", "Things that are nobody else's business.")

        assert "Shopee's account system" in _master(home).read_text(encoding="utf-8")

        resp = client.post("/api/v1/resources/knowledge/shopee/disable")
        assert resp.status_code == 200, resp.text

        text = _master(home).read_text(encoding="utf-8")

    assert "Shopee's account system" not in text
    assert "shopee" not in text
    assert "nobody else's business" in text


@pytest.mark.acceptance(
    spec="skill-manager", scenario="Coffer's own skill is rewritten from the build at every start"
)
def test_a_second_boot_rewrites_rather_than_duplicates(home) -> None:  # type: ignore[no-untyped-def]
    """Seeding is idempotent: it heals an edited master instead of stacking
    another folder beside it, and writes nothing when nothing moved."""
    config_dir = home / "agent-cfg"
    config_dir.mkdir()

    with _client() as client:
        _seed_collection(client, "shopee", "Internal systems.")
        _register_agent(client, "delivered-to", config_dir)
    with _client():
        pass

    master = _master(home)
    original = master.read_text(encoding="utf-8")
    master.write_text("someone edited this\n", encoding="utf-8")

    with _client():
        pass

    assert master.read_text(encoding="utf-8") == original
    assert sorted(p.name for p in (config_dir / "skills").iterdir()) == [GUIDE_SKILL_NAME]
    assert sorted(p.name for p in (home / ".coffer" / "skills").iterdir()) == [GUIDE_SKILL_NAME]


def test_the_seed_writes_nothing_when_the_catalogue_has_not_moved(home) -> None:  # type: ignore[no-untyped-def]
    """An unchanged boot must leave the row alone.

    It runs at every start, so a seed that rewrote unconditionally would bump
    ``updated_at`` and audit a skill update on every launch — events describing
    nothing, in a log whose whole value is that its entries mean something.
    """
    with _client() as client:
        _seed_collection(client, "shopee", "Internal systems.")
    with _client() as client:
        first = client.get(f"/api/v1/skills/{GUIDE_SKILL_NAME}").json()

    with _client() as client:
        second = client.get(f"/api/v1/skills/{GUIDE_SKILL_NAME}").json()

    assert second["updated_at"] == first["updated_at"]
    assert second["version_hash"] == first["version_hash"]


def test_a_changed_catalogue_does_rewrite_the_guide(home) -> None:  # type: ignore[no-untyped-def]
    """The other half of idempotence: unchanged is quiet, changed is written.

    Without this, a seed that never wrote anything would pass the test above.
    """
    with _client() as client:
        _seed_collection(client, "shopee", "Internal systems.")
    with _client() as client:
        first = client.get(f"/api/v1/skills/{GUIDE_SKILL_NAME}").json()
        _seed_collection(client, "coffer", "Notes an agent wrote while working on Coffer.")

    with _client() as client:
        second = client.get(f"/api/v1/skills/{GUIDE_SKILL_NAME}").json()

    assert second["version_hash"] != first["version_hash"]
    assert "Notes an agent wrote" in _master(home).read_text(encoding="utf-8")


def _upgrade_from_0088(home: pathlib.Path, config_dir: pathlib.Path) -> None:
    """Put a vault at the revision before the retirement, with one agent, then
    run the retirement.

    A migration runs once, against the vault as it stands at that moment — so
    the only honest way to test this one is to build that moment. Booting the
    app instead would register the agent AFTER 0089 had already swept, and the
    test would pass by finding nothing to do.
    """
    db = home / "c.db"
    cfg = AlembicConfig(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "0088")
    agent_cfg = {"type": "claude_code", "config_dir": str(config_dir)}
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO resources (kind, name, config_json, enabled, created_at, updated_at) "
            "VALUES ('agent', 'delivered-to', ?, 1, '2026-01-01', '2026-01-01')",
            (json.dumps(agent_cfg),),
        )
        conn.commit()
    command.upgrade(cfg, "0089")


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="migration removes the retired knowledge skill and spares a foreign folder",
)
def test_the_retired_knowledge_skill_is_removed_from_every_agent(home) -> None:  # type: ignore[no-untyped-def]
    """The folder the old delivery left has no binding, so nothing but this
    migration can reclaim it — and left alone it would keep describing a
    contract that has moved, never to be rewritten again."""
    config_dir = home / "agent-cfg"
    retired = config_dir / "skills" / _RETIRED
    retired.mkdir(parents=True)
    (retired / "SKILL.md").write_text("old\n", encoding="utf-8")
    (retired / "README.md").write_text("# Generated\n", encoding="utf-8")

    _upgrade_from_0088(home, config_dir)

    assert not retired.exists()


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="migration removes the retired knowledge skill and spares a foreign folder",
)
def test_a_foreign_folder_at_the_retired_name_is_left_alone(home) -> None:  # type: ignore[no-untyped-def]
    """Only what Coffer itself wrote is removed. A skill somebody else put at
    that name is theirs, and deleting it on the strength of a folder name would
    be destroying work."""
    config_dir = home / "agent-cfg"
    mine = config_dir / "skills" / _RETIRED
    mine.mkdir(parents=True)
    (mine / "SKILL.md").write_text("---\nname: coffer-knowledge\ndescription: mine\n---\n")

    _upgrade_from_0088(home, config_dir)

    assert mine.is_dir()
    assert "mine" in (mine / "SKILL.md").read_text(encoding="utf-8")


def test_the_master_folder_carries_no_machine_specific_provenance(home) -> None:  # type: ignore[no-untyped-def]
    """The master converges to the user's other machines (spec vault-sync), and
    it is regenerated locally at every boot. A timestamp or a path in its meta
    file would leave two vaults overwriting each other forever."""
    with _client():
        pass

    meta = home / ".coffer" / "skills" / GUIDE_SKILL_NAME / ".coffer.meta.json"
    assert meta.is_file()
    assert json.loads(meta.read_text(encoding="utf-8")) == {
        "name": GUIDE_SKILL_NAME,
        "source": {"type": "builtin"},
    }
