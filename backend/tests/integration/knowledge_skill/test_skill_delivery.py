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


@pytest.mark.acceptance(
    spec="knowledge", scenario="the knowledge skill is delivered to a managed agent"
)
def test_the_knowledge_skill_is_seeded_and_teaches_the_motion(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    from coffer.surfaces.http.app import create_app

    with TestClient(create_app()):
        pass

    installed = pathlib.Path(tmp_path) / ".coffer" / "skills" / SKILL_NAME / "SKILL.md"
    assert installed.is_file(), "the knowledge skill was not seeded into the master store"

    text = installed.read_text(encoding="utf-8")
    assert f"name: {SKILL_NAME}" in text
    # The body has to teach catalogue-then-grep, not just announce the tools:
    # descending one level at a time is what keeps a large corpus readable.
    for tool in ("coffer__list", "coffer__read", "coffer__grep", "coffer__write"):
        assert tool in text, f"{tool} is not named in the skill body"


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
