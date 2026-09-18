"""The delivered skill: the whole of what an agent is ever told.

With no retrieval tool (spec knowledge FR-033), this file *is* the layer's
interface to a model. Two things therefore have to hold, and both are tested
here rather than assumed: the description carries subjects a model can match on
(FR-036), and the body carries every document's path plus the absolute root so
nothing has to be guessed (FR-037).

The rendering is the same for every agent — a collection carries no per-agent
reach — so what the tests below pin about delivery is the other axis: a
*disabled* collection is in nobody's copy, and each agent still gets its own
real file rather than a shared one (FR-035).
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
from coffer.infrastructure.knowledge import fs, paths


def _entry(name: str, description: str, source_count: int, topic_count: int) -> CollectionEntry:
    """A catalogue entry, built by KEYWORD.

    These were positional until `CollectionEntry` grew its `uid` as the first
    field, at which point every argument silently shifted one place and a
    `description` became an `int` — a break no type checker could see, because
    the shifted values were still a `str` and an `int`. One helper, named
    arguments, and the next field to arrive cannot do it again.
    """
    return CollectionEntry(
        uid=f"uid-{name}",
        name=name,
        description=description,
        source_count=source_count,
        topic_count=topic_count,
    )


def _resource(rid: int, name: str, *, enabled: bool = True) -> Resource:
    now = datetime.now(tz=UTC)
    return Resource(
        id=rid,
        uid=f"uid-{rid}",
        kind=KIND_KNOWLEDGE,
        name=name,
        description=None,
        config={},
        enabled=enabled,
        created_at=now,
        updated_at=now,
        scope=None,
    )


class _Resources:
    """A fake registry that honours the ``enabled`` filter, because that filter
    is now the only thing standing between a collection and every agent."""

    def __init__(self, rows: list[Resource]) -> None:
        self._rows = rows

    async def list(self, kind=None, enabled=None):  # type: ignore[no-untyped-def]
        return [r for r in self._rows if enabled is None or r.enabled is enabled]


class _Audit:
    async def record(self, event_type, **kwargs):  # type: ignore[no-untyped-def]
        return None


class _Agent:
    def __init__(self, name: str) -> None:
        self.name = name


@pytest.fixture
def corpus(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    """Two collections on disk, ``shopee`` and ``personal``, one topic each."""
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


def _service(rows: list[Resource]) -> KnowledgeService:
    return KnowledgeService(resources=_Resources(rows), audit=_Audit())


@pytest.fixture
def service(corpus) -> KnowledgeService:  # type: ignore[no-untyped-def]
    return _service([_resource(1, "shopee"), _resource(2, "personal")])


# ----- what the description says ------------------------------------------


def test_the_description_names_subjects_rather_than_the_layer() -> None:
    catalogue = [
        (_entry("shopee", "Shopee's account system and its platforms.", 3, 4), ()),
        (_entry("personal", "Notes about the side project.", 1, 1), ()),
    ]
    described = render_description(catalogue)
    # The point of the rewrite: a model working on the account system has
    # something here to recognise. The version this replaced said only that
    # Coffer holds "a fact about THIS user's working environment".
    assert "Shopee's account system" in described
    assert "side project" in described
    assert len(described) <= MAX_DESCRIPTION_CHARS


def test_the_description_drops_subjects_rather_than_overflowing() -> None:
    catalogue = [(_entry(f"c{n}", "x" * 200, 1, 1), ()) for n in range(20)]
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
    catalogue = await service.catalogue()
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
    text = render(str(corpus), await service.catalogue())
    assert "Nothing curated here yet" in text


# ----- what reaches which agent -------------------------------------------


@pytest.mark.acceptance(
    spec="knowledge", scenario="a disabled collection is absent from every agent's skill"
)
@pytest.mark.anyio
async def test_a_disabled_collection_reaches_no_agent_and_an_enabled_one_reaches_all(  # type: ignore[no-untyped-def]
    corpus, tmp_path
) -> None:
    """``enabled`` is the whole of the gate, and it is not per agent.

    ``shopee`` is switched off while its directory and its topic document sit
    right there on disk, so this is the registry's answer being honoured rather
    than an empty folder looking the same as a withheld one.
    """
    service = _service([_resource(1, "shopee", enabled=False), _resource(2, "personal")])
    dirs = {
        "claude-code": tmp_path / "claude" / "skills",
        "codex": tmp_path / "codex" / "skills",
    }
    for d in dirs.values():
        d.mkdir(parents=True)
    delivery = KnowledgeSkillDelivery(
        service=service,
        list_agents=_agents_returning([_Agent("claude-code"), _Agent("codex")]),
        resolve_skill_dir=lambda a: dirs[a.name],  # type: ignore[union-attr]
    )
    assert await delivery.deliver_all() == 2

    assert paths.topics_dir("shopee").is_dir(), "the directory is still there"
    for name, directory in dirs.items():
        text = (directory / "coffer-knowledge" / "SKILL.md").read_text(encoding="utf-8")
        # The enabled one reaches every agent, catalogue and all.
        assert "personal" in text, name
        assert "deploy-notes.md" in text, name
        # The disabled one reaches none of them — not its name, not its
        # description, not a path inside it.
        assert "shopee" not in text, name
        assert "account system" not in text, name
        assert "session-who-owns-login-state.md" not in text, name


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
    # master here. Nothing regenerates that master, so writing through the link
    # would leave the corpus's one stale copy in circulation — it has to be
    # replaced rather than followed.
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
    # Identical text, because every agent is told the same thing — but two
    # separate files, each inside the directory its own agent reads.
    assert files["claude-code"].read_text() == files["codex"].read_text()
    assert not files["claude-code"].samefile(files["codex"])


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
