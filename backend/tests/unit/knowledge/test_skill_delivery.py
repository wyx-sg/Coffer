"""The delivered skill: the whole of what an agent is ever told.

With no retrieval tool (spec knowledge FR-033), this file *is* the layer's
interface to a model. Two things therefore have to hold, and both are tested
here rather than assumed: the description carries subjects a model can match on
(FR-036), and the body carries every document's path plus the absolute root so
nothing has to be guessed (FR-037).

Authorization moved here too. A collection an agent is not activated for must
not appear in that agent's copy at all — not its name, not its description, not
a path inside it (FR-010).
"""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.application.knowledge.skill_delivery import KnowledgeSkillDelivery
from coffer.application.knowledge.skill_render import (
    MAX_DESCRIPTION_CHARS,
    render,
    render_description,
)
from coffer.domain.knowledge.entry import CollectionEntry
from coffer.domain.resource import Resource
from coffer.domain.scope import Scope
from coffer.infrastructure.knowledge import fs, paths


def _resource(rid: int, name: str, scope: Scope | None) -> Resource:
    now = datetime.now(tz=UTC)
    return Resource(
        id=rid,
        kind=KIND_KNOWLEDGE,
        name=name,
        description=None,
        config={},
        enabled=True,
        created_at=now,
        updated_at=now,
        scope=scope,
    )


class _Resources:
    def __init__(self, rows: list[Resource]) -> None:
        self._rows = rows

    async def list(self, kind=None, enabled=None):  # type: ignore[no-untyped-def]
        return list(self._rows)


class _Audit:
    async def record(self, event_type, **kwargs):  # type: ignore[no-untyped-def]
        return None


class _Agent:
    def __init__(self, name: str) -> None:
        self.name = name


@pytest.fixture
def corpus(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    """Two collections: ``shopee`` restricted to claude-code, ``personal`` open."""
    root = tmp_path / "knowledge"
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(root))
    for name, blurb in (
        ("shopee", "Shopee's account system, its data plane and the platforms around it."),
        ("personal", "Notes about the side project."),
    ):
        fs.create_collection_dir(name)
        paths.readme_path(name).write_text(f"# {name}\n\n{blurb}\n", encoding="utf-8")
    fs.write_file(
        directory="shopee/topics",
        title="session — who owns login state",
        description="Which service issues, checks and revokes a login token.",
        body="account.session owns it.",
    )
    fs.write_file(
        directory="personal/topics", title="Deploy notes", description="How it ships.", body="b"
    )
    return root


@pytest.fixture
def service(corpus) -> KnowledgeService:  # type: ignore[no-untyped-def]
    return KnowledgeService(
        resources=_Resources(
            [
                _resource(1, "shopee", Scope(agents=["claude-code"])),
                _resource(2, "personal", None),
            ]
        ),
        audit=_Audit(),
    )


# ----- what the description says ------------------------------------------


def test_the_description_names_subjects_rather_than_the_layer() -> None:
    catalogue = [
        (CollectionEntry("shopee", "Shopee's account system and its platforms.", 3, 4), ()),
        (CollectionEntry("personal", "Notes about the side project.", 1, 1), ()),
    ]
    described = render_description(catalogue)
    # The point of the rewrite: a model working on the account system has
    # something here to recognise. The version this replaced said only that
    # Coffer holds "a fact about THIS user's working environment".
    assert "Shopee's account system" in described
    assert "side project" in described
    assert len(described) <= MAX_DESCRIPTION_CHARS


def test_the_description_drops_subjects_rather_than_overflowing() -> None:
    catalogue = [(CollectionEntry(f"c{n}", "x" * 200, 1, 1), ()) for n in range(20)]
    described = render_description(catalogue)
    assert len(described) <= MAX_DESCRIPTION_CHARS
    # Truncation drops whole subjects from the tail; it never cuts one open.
    assert described.rstrip().endswith(".")


def test_an_empty_corpus_still_describes_itself() -> None:
    assert "Nothing has been filed yet" in render_description([])


# ----- what the body says --------------------------------------------------


@pytest.mark.acceptance(
    spec="knowledge", scenario="the skill body carries the catalogue and the absolute root"
)
@pytest.mark.anyio
async def test_the_body_carries_every_document_and_the_absolute_root(service, corpus) -> None:  # type: ignore[no-untyped-def]
    catalogue = await service.catalogue("claude-code")
    text = render(str(corpus), catalogue)

    assert str(corpus) in text
    for expected in (
        "session-who-owns-login-state.md",
        "session — who owns login state",
        "Which service issues, checks and revokes a login token.",
        "deploy-notes.md",
    ):
        assert expected in text, expected
    # It points at the agent's own tools, and names the one tool that remains.
    assert "your own file tools" in text
    assert "coffer__write" in text
    # Nothing tells the agent to call a reading tool, because there is none.
    for gone in ("coffer__read", "coffer__list", "coffer__grep", "coffer__search"):
        assert gone not in text, gone


@pytest.mark.anyio
async def test_a_collection_with_no_documents_says_so_rather_than_looking_empty(
    service, corpus
) -> None:  # type: ignore[no-untyped-def]
    fs.delete_file("personal/topics/deploy-notes.md")
    text = render(str(corpus), await service.catalogue("claude-code"))
    assert "Nothing curated here yet" in text


# ----- authorization at delivery ------------------------------------------


@pytest.mark.acceptance(
    spec="knowledge", scenario="a collection outside an agent's scope is absent from its skill"
)
@pytest.mark.anyio
async def test_an_unauthorized_collection_is_absent_from_the_other_agent_s_copy(
    service, corpus
) -> None:  # type: ignore[no-untyped-def]
    mine = render(str(corpus), await service.catalogue("claude-code"))
    theirs = render(str(corpus), await service.catalogue("codex"))

    assert "shopee" in mine and "personal" in mine
    # Not the name, not the description, not a path inside it: naming a
    # collection the caller may not have is itself the disclosure.
    assert "shopee" not in theirs
    assert "account system" not in theirs
    assert "session-who-owns-login-state.md" not in theirs
    assert "personal" in theirs


@pytest.mark.acceptance(
    spec="knowledge", scenario="the two agents' skill files are independent copies"
)
@pytest.mark.anyio
async def test_each_agent_gets_real_bytes_and_a_stale_symlink_is_replaced(  # type: ignore[no-untyped-def]
    service, corpus, tmp_path
) -> None:
    dirs = {
        "claude-code": tmp_path / "claude" / "skills",
        "codex": tmp_path / "codex" / "skills",
    }
    for d in dirs.values():
        d.mkdir(parents=True)

    # A vault upgraded from the previous delivery has a symlink into one shared
    # master here. Writing through it would edit the copy every other agent
    # points at, so it has to be replaced rather than followed.
    master = tmp_path / "master" / "coffer-knowledge"
    master.mkdir(parents=True)
    (master / "SKILL.md").write_text("the old shared one\n", encoding="utf-8")
    (dirs["codex"] / "coffer-knowledge").symlink_to(master, target_is_directory=True)

    delivery = KnowledgeSkillDelivery(
        service=service,
        list_agents=_agents_returning([_Agent("claude-code"), _Agent("codex")]),
        resolve_skill_dir=lambda a: dirs[a.name],  # type: ignore[union-attr]
    )
    assert await delivery.deliver_all() == 2

    files = {name: directory / "coffer-knowledge" / "SKILL.md" for name, directory in dirs.items()}
    for path in files.values():
        assert not path.is_symlink()
        assert not path.parent.is_symlink()
    assert (master / "SKILL.md").read_text(encoding="utf-8") == "the old shared one\n"
    # Independent bytes, and they differ — which is what makes delivery the
    # place authorization is enforced.
    assert files["claude-code"].read_text() != files["codex"].read_text()


@pytest.mark.anyio
async def test_one_unwritable_agent_does_not_stop_the_others(service, corpus, tmp_path) -> None:  # type: ignore[no-untyped-def]
    good = tmp_path / "good" / "skills"
    good.mkdir(parents=True)

    def _resolve(agent: Any) -> pathlib.Path:
        if agent.name == "broken":
            raise OSError("no such directory")
        return good

    delivery = KnowledgeSkillDelivery(
        service=service,
        list_agents=_agents_returning([_Agent("broken"), _Agent("claude-code")]),
        resolve_skill_dir=_resolve,
    )
    # Delivery is best-effort: the corpus is still readable at paths a person
    # can give an agent, so a failure here must not fail whatever armed it.
    assert await delivery.deliver_all() == 1
    assert (good / "coffer-knowledge" / "SKILL.md").is_file()


@pytest.mark.anyio
async def test_an_unchanged_copy_is_not_rewritten(service, corpus, tmp_path) -> None:  # type: ignore[no-untyped-def]
    skills = tmp_path / "claude" / "skills"
    skills.mkdir(parents=True)
    delivery = KnowledgeSkillDelivery(
        service=service,
        list_agents=_agents_returning([_Agent("claude-code")]),
        resolve_skill_dir=lambda a: skills,
    )
    assert await delivery.deliver_all() == 1
    written = skills / "coffer-knowledge" / "SKILL.md"
    stamp = written.stat().st_mtime_ns

    # Delivery runs on every worker tick, so the common case must cost a
    # comparison rather than a write — otherwise two files are rewritten every
    # minute forever, and every one of those writes is a vault change sync has
    # to carry.
    assert await delivery.deliver_all() == 0
    assert written.stat().st_mtime_ns == stamp

    # A corpus that actually changed is delivered again.
    fs.write_file(directory="personal/topics", title="Something new", description="d", body="b")
    assert await delivery.deliver_all() == 1


def _agents_returning(agents: list[_Agent]):  # type: ignore[no-untyped-def]
    async def _list() -> list[_Agent]:
        return agents

    return _list
