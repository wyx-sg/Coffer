"""The curation pass, and the boundaries that make it safe to run unattended.

Curation rewrites ``topics/`` with no review step (spec knowledge FR-021). What
makes that acceptable is not a safety net after the fact but three properties
checked here: it cannot reach ``sources/`` at all, it cannot write more than a
handful of files, and it cannot record a reference that will rot. The fourth —
that a source it did not finish absorbing stays owed — is the watermark, tested
in ``test_two_lanes``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.engine_timeout import DEFAULT_MODEL_TIMEOUT_S
from coffer.application.knowledge.curate import CURATION_SYSTEM, run_curation
from coffer.application.knowledge.curate_tools import (
    MAX_WRITES_PER_PASS,
    Counters,
    build_tools,
    offending_reference,
)
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.domain.errors import ResourceNotFound
from coffer.domain.resource import Resource
from coffer.infrastructure.knowledge import catalogue, fs, paths


class _Resources:
    def __init__(self, names: list[str]) -> None:
        now = datetime.now(tz=UTC)
        self._rows = [
            Resource(
                id=i,
                # A uid a test can spell, and deliberately not the name: a
                # lookup that worked because the two matched would prove
                # nothing about addressing a collection by identity.
                uid=f"uid-{i}",
                kind=KIND_KNOWLEDGE,
                name=n,
                description=None,
                config={},
                enabled=True,
                created_at=now,
                updated_at=now,
                scope=None,
            )
            for i, n in enumerate(names, start=1)
        ]

    async def get(self, uid):  # type: ignore[no-untyped-def]
        for row in self._rows:
            if row.uid == uid:
                return row
        raise ResourceNotFound(uid)

    def uid_of(self, name: str) -> str:
        """The uid a test knows the collection by its name — the resolution a
        person's CLI or the web page does before anything inside the daemon
        is handed an identity."""
        return next(r.uid for r in self._rows if r.name == name)

    async def list(self, kind=None, enabled=None):  # type: ignore[no-untyped-def]
        return list(self._rows)


class _Audit:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def record(self, event_type, **kwargs):  # type: ignore[no-untyped-def]
        self.events.append(event_type)


class _NoModel:
    async def get_default(self):  # type: ignore[no-untyped-def]
        return None


class _Model:
    def __init__(self, connection: Any = "conn") -> None:
        self._connection = connection

    async def get_default(self):  # type: ignore[no-untyped-def]
        return type("C", (), {"model": "fake-model"})()


class _Loop:
    """An agentic loop scripted to make a fixed sequence of tool calls."""

    def __init__(self, calls: list[tuple[str, dict[str, Any]]]) -> None:
        self._calls = calls
        self.prompt = ""
        self.timeout: float | None = None
        self.results: list[dict[str, Any]] = []

    async def run(
        self,
        *,
        model,
        tools,
        system_prompt,
        user_prompt,
        credential_resolver,
        recursion_limit,
        timeout=None,
    ):  # type: ignore[no-untyped-def]
        # Recorded, not merely accepted: curation's turns were the one model
        # call in Coffer with no bound at all, so "the bound arrives here" is
        # the thing worth asserting.
        self.timeout = timeout
        # The rules are the system turn and the brief is the human turn; the
        # assertions below read the brief, so that is what `prompt` holds.
        self.system = system_prompt
        self.prompt = user_prompt
        self.tool_names = sorted(t.name for t in tools)
        by_name = {t.name: t for t in tools}
        for name, args in self._calls:
            self.results.append(await by_name[name].handler(args))
        return {}


@pytest.fixture(autouse=True)
def knowledge_root(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    root = tmp_path / "knowledge"
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(root))
    fs.create_collection_dir("shopee")
    return root


#: The one collection every test here works in, and the uid the pass is aimed
#: at. Spelled out rather than derived from the name: the pass resolves an
#: identity, and a test whose identity IS the name would not notice if it
#: stopped doing so.
_SHOPEE_UID = "uid-1"


def _service() -> KnowledgeService:
    return KnowledgeService(resources=_Resources(["shopee"]), audit=_Audit())


def _source(title: str = "Session facts", body: str = "`account.session` owns login state") -> str:
    return fs.write_file(
        directory="shopee/sources", title=title, description="d", body=body, actor="user"
    ).path


def _topic(title: str, body: str = "b", description: str = "d") -> str:
    return fs.write_file(
        directory="shopee/topics", title=title, description=description, body=body
    ).path


async def _run(loop: _Loop, models: Any = None, **kwargs: Any) -> dict[str, Any]:
    return await run_curation(
        _service(),
        _SHOPEE_UID,
        agent=loop,
        models=models or _Model(),
        credential_resolver=lambda ref: "key",
        **kwargs,
    )


# ----- statuses ------------------------------------------------------------


@pytest.mark.acceptance(
    spec="knowledge", scenario="curation is a no-op when no internal model is configured"
)
@pytest.mark.anyio
async def test_no_model_writes_nothing_and_leaves_the_source_owed(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    relpath = _source()
    outcome = await _run(_Loop([]), models=_NoModel())
    assert outcome["status"] == "no_model"
    assert catalogue.count_files(paths.topics_dir("shopee")) == 0
    # The watermark stays unset, so the material is curated once a model is
    # configured rather than skipped forever.
    assert fs.read_file(relpath).ingested_at == ""
    assert fs.pending_sources("shopee") == (relpath,)


@pytest.mark.anyio
async def test_nothing_pending_is_up_to_date(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    assert (await _run(_Loop([])))["status"] == "up_to_date"


@pytest.mark.anyio
async def test_a_loop_that_raises_leaves_the_source_owed(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    relpath = _source()

    class _Boom:
        async def run(self, **kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("provider exploded")

    outcome = await _run(_Boom())  # type: ignore[arg-type]
    assert outcome["status"] == "failed"
    assert fs.read_file(relpath).ingested_at == ""


# ----- what the pass may touch --------------------------------------------


@pytest.mark.acceptance(
    spec="knowledge", scenario="curation writes topics and never touches sources"
)
@pytest.mark.anyio
async def test_a_pass_writes_topics_and_leaves_sources_byte_identical(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    relpath = _source(body="one fact")
    other = _source(title="Second", body="another fact")
    before = paths.resolve(other).read_bytes()

    loop = _Loop(
        [
            (
                "write_topic",
                {
                    "title": "Session",
                    "description": "who owns login state",
                    "body": "one fact and another",
                },
            )
        ]
    )
    outcome = await _run(loop, source_relpath=relpath)

    assert outcome["status"] == "ok"
    assert [f.path for f in catalogue.walk_files(paths.topics_dir("shopee"))] == [
        "shopee/topics/session.md"
    ]
    # The source that was absorbed gained only its stamp; the untouched one is
    # byte-for-byte what it was.
    assert paths.resolve(other).read_bytes() == before
    assert fs.read_file(relpath).ingested_at != ""


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="a pass sees candidates and the catalogue, never the sources lane",
)
@pytest.mark.anyio
async def test_the_tool_surface_cannot_reach_the_sources_lane(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    relpath = _source(body="`account.session` owns login state")
    _topic("Login state", body="`account.session` is involved somehow")
    _topic("Unrelated", body="nothing in common")

    loop = _Loop([("read_topic", {"path": relpath})])
    await _run(loop, source_relpath=relpath)

    # Four tools, none of which names the other lane.
    assert loop.tool_names == ["list_topics", "read_topic", "retire_topic", "write_topic"]
    # And the one call that tried to read a source was refused rather than served.
    assert "error" in loop.results[0]
    assert "topics/" in loop.results[0]["error"]

    # The brief carries the source, the catalogue, and the candidate that
    # actually matched — the catalogue so the model can decide none of them fit.
    assert "account.session" in loop.prompt
    assert "shopee/topics/login-state.md" in loop.prompt
    assert "shopee/topics/unrelated.md" in loop.prompt


@pytest.mark.acceptance(spec="knowledge", scenario="a pass is bounded to a handful of writes")
@pytest.mark.anyio
async def test_a_pass_stops_at_the_write_bound(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    relpath = _source()
    attempts = MAX_WRITES_PER_PASS + 3
    loop = _Loop(
        [
            ("write_topic", {"title": f"Doc {n}", "description": "d", "body": f"body {n}"})
            for n in range(attempts)
        ]
    )
    outcome = await _run(loop, source_relpath=relpath)

    assert outcome["written"] == MAX_WRITES_PER_PASS
    refused = [r for r in loop.results if "error" in r]
    assert len(refused) == attempts - MAX_WRITES_PER_PASS
    assert str(MAX_WRITES_PER_PASS) in refused[0]["error"]
    # What did land is whole files, not truncated ones.
    written = catalogue.walk_files(paths.topics_dir("shopee"))
    assert len(written) == MAX_WRITES_PER_PASS
    assert all(fs.read_file(f.path).body.strip().startswith("body") for f in written)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("folder", "expected"),
    [
        ("", "shopee/topics/doc.md"),
        ("account", "shopee/topics/account/doc.md"),
        ("shopee/topics", "shopee/topics/doc.md"),
        ("shopee/topics/account", "shopee/topics/account/doc.md"),
        ("topics/account", "shopee/topics/account/doc.md"),
        ("/account/", "shopee/topics/account/doc.md"),
    ],
)
async def test_a_folder_lands_inside_the_lane_however_it_is_spelled(
    knowledge_root, folder: str, expected: str
) -> None:  # type: ignore[no-untyped-def]
    # Found by running a real pass, not by any fake: a model shown paths like
    # `shopee/topics/x.md` answers with `folder="shopee/topics"`, which used to
    # produce `shopee/topics/shopee/topics/x.md`. The prefixes this layer adds
    # are stripped rather than the spelling being refused.
    relpath = _source()
    loop = _Loop(
        [("write_topic", {"folder": folder, "title": "Doc", "description": "d", "body": "b"})]
    )
    await _run(loop, source_relpath=relpath)
    assert loop.results[0]["path"] == expected


# ----- the reference rule --------------------------------------------------


@pytest.mark.acceptance(spec="knowledge", scenario="a curated topic carries no file-name reference")
@pytest.mark.anyio
async def test_a_write_naming_a_knowledge_file_is_refused(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    relpath = _source()
    _topic("Login state")

    loop = _Loop(
        [
            (
                "write_topic",
                {"title": "Session", "description": "d", "body": "see `login-state.md` for more"},
            ),
            (
                "write_topic",
                {
                    "title": "Session",
                    "description": "d",
                    "body": "the login-state document covers it",
                },
            ),
        ]
    )
    await _run(loop, source_relpath=relpath)

    assert "error" in loop.results[0] and "login-state.md" in loop.results[0]["error"]
    # The rewrite that names the subject instead of the file goes through.
    assert loop.results[1].get("ok") is True


def test_only_this_corpus_s_file_names_are_refused() -> None:
    known = frozenset({"login-state.md"})
    # A document about a repository may legitimately mention that repository's
    # own files; refusing that would be a rule the model cannot satisfy.
    assert offending_reference("the repo's `AGENTS.md` says so", known, collection="shopee") is None
    # A repository of its own may hold a `sources/` folder; that is not this
    # corpus, and refusing it would be a rule the model cannot satisfy.
    assert offending_reference("see `docs/sources/overview.md`", known, collection="shopee") is None
    assert (
        offending_reference("see `login-state.md`", known, collection="shopee") == "login-state.md"
    )
    # A path into THIS collection's lanes is this corpus by construction.
    assert (
        offending_reference("shopee/topics/anything.md", known, collection="shopee")
        == "shopee/topics/anything.md"
    )


@pytest.mark.acceptance(
    spec="knowledge", scenario="the pass is instructed that a contradicting source wins"
)
def test_the_system_prompt_states_the_contradiction_rule() -> None:
    # No code can adjudicate a contradiction, so the instructions are the whole
    # of FR-026 and this is what pins them.
    lowered = CURATION_SYSTEM.lower()
    assert "the source wins" in lowered
    assert "previously recorded" in lowered
    assert "corrected" in lowered
    # And the bound the model is told about matches the one enforced.
    assert str(MAX_WRITES_PER_PASS) in CURATION_SYSTEM


def test_retire_is_bounded_like_a_write(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    # Retiring is a write of the corpus too, so it counts against the same
    # bound — otherwise a pass could empty a collection for free.
    counters = Counters()
    counters.written = MAX_WRITES_PER_PASS
    tools = {
        t.name: t
        for t in build_tools(
            service=_service(), collection="shopee", actor="system", counters=counters
        )
    }
    assert counters.writes == MAX_WRITES_PER_PASS
    assert "retire_topic" in tools


async def test_every_turn_of_the_loop_carries_the_operators_bound() -> None:
    """Curation's turns were the one model call in Coffer with no bound at all.

    A wedged endpoint therefore held the pass until the daemon restarted, and
    nothing on any surface said so. The bound travels to the CLIENT rather than
    around the call because the loop is one ``await`` from out here — wrapping
    it could bound the whole conversation or nothing, and neither is "each turn
    gets a fair chance and then gives up".
    """
    _source()
    loop = _Loop([])

    async def chosen() -> int | None:
        return 150

    await _run(loop, read_timeout=chosen)

    assert loop.timeout == 150.0


async def test_a_pass_with_no_settings_to_consult_still_has_a_bound() -> None:
    # The unit-test construction, and any pass built before the singleton
    # exists. Making the bound configurable must not make it optional.
    _source()
    loop = _Loop([])

    await _run(loop)

    assert loop.timeout == DEFAULT_MODEL_TIMEOUT_S
