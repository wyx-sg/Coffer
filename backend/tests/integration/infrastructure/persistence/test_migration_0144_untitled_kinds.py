"""Revision 0144 strips ``title`` from the resource files of kinds that carry none.

``memory`` partition files (``derived/``), ``mcp_server`` and ``skill`` files
(``vault/``) lose the key; a ``provider`` file keeps its title; the rest of each
file is untouched; a second run changes nothing.
"""

from __future__ import annotations

import json
import pathlib

from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
)


def _write(path: pathlib.Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n")


def test_untitled_kinds_lose_the_key_and_titled_kinds_keep_it(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'runs.db'}")
    files = {
        "derived/resources/memory/p.json": ("memory", "Mine"),
        "vault/resources/mcp_server/m.json": ("mcp_server", "Team search"),
        "vault/resources/skill/s.json": ("skill", "Pdf"),
        "vault/resources/provider/x.json": ("provider", "Work"),
    }
    for rel, (kind, title) in files.items():
        _write(
            tmp_path / rel,
            {
                "uid": "u",
                "kind": kind,
                "name": "n",
                "title": title,
                "description": "d",
                "config": {},
            },
        )
    cfg = _alembic_config()
    command.upgrade(cfg, "0143")

    command.upgrade(cfg, "0144")

    memory = json.loads((tmp_path / "derived/resources/memory/p.json").read_text())
    assert "title" not in memory
    assert list(memory) == ["uid", "kind", "name", "description", "config"]
    assert "title" not in json.loads((tmp_path / "vault/resources/mcp_server/m.json").read_text())
    assert "title" not in json.loads((tmp_path / "vault/resources/skill/s.json").read_text())
    assert json.loads((tmp_path / "vault/resources/provider/x.json").read_text())["title"] == "Work"

    before = (tmp_path / "derived/resources/memory/p.json").read_bytes()
    command.downgrade(cfg, "0143")
    command.upgrade(cfg, "0144")
    assert (tmp_path / "derived/resources/memory/p.json").read_bytes() == before
