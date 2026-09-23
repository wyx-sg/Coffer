"""The curation pass, and the boundaries that make it safe to run unattended.

Curation rewrites a collection's documents with no review step (spec knowledge
"Curate through a fenced four-tool pass"). What makes that acceptable is not a
safety net after the fact but the properties checked here: it is fenced to one
collection's documents, it cannot write more than a handful of files, it cannot
record a reference that will rot, and an item it did not finish absorbing stays
owed — material stays in the inbox, an edited document stays unstamped.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.engine_timeout import DEFAULT_MODEL_TIMEOUT_S
from coffer.application.knowledge.curate import CURATION_SYSTEM, pending_items, run_curation
from coffer.application.knowledge.curate_tools import (
    MAX_WRITES_PER_PASS,
    Counters,
    build_tools,
    offending_reference,
)
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.domain.errors import ResourceNotFound
from coffer.domain.knowledge.entry import Pending
from coffer.domain.knowledge.errors import UnsafeKnowledgePath
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


def _material(
    title: str = "Session facts", body: str = "`account.session` owns login state"
) -> str:
    """New material in the inbox — what an upload or ``coffer__write`` leaves."""
    return fs.submit_material("shopee", title=title, description="d", body=body, actor="user")


def _document(title: str, body: str = "b", description: str = "d") -> str:
    """A document curation has already seen."""
    return fs.write_file(
        directory="shopee", title=title, description=description, body=body, curated=True
    ).path


def _documents() -> list[str]:
    return [f.path for f in catalogue.walk_files(paths.collection_dir("shopee"))]


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
    spec="knowledge",
    scenario="with no internal model, pending material becomes documents as it stands",
)
@pytest.mark.anyio
async def test_no_model_promotes_the_inbox_as_it_stands(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    _material(title="Session facts", body="one fact")
    _material(title="Gateway", body="another fact")
    outcome = await _run(_Loop([]), models=_NoModel())

    assert outcome["status"] == "no_model"
    assert sorted(outcome["promoted"]) == ["shopee/gateway.md", "shopee/session-facts.md"]
    assert fs.inbox_items("shopee") == ()
    # Promoted as it stood, and stamped: nothing is going to curate it, so an
    # unstamped document would only be handed back by every sweep.
    promoted = fs.read_file("shopee/session-facts.md")
    assert promoted.body.strip() == "one fact"
    assert promoted.curated_at != ""
    assert pending_items("shopee") == ()


@pytest.mark.anyio
async def test_nothing_pending_is_up_to_date(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    assert (await _run(_Loop([])))["status"] == "up_to_date"


@pytest.mark.anyio
async def test_a_loop_that_raises_leaves_the_material_owed(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    name = _material()

    class _Boom:
        async def run(self, **kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("provider exploded")

    outcome = await _run(_Boom())  # type: ignore[arg-type]
    assert outcome["status"] == "failed"
    assert fs.inbox_items("shopee") == (name,)


# ----- what the pass does with its item ------------------------------------


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="curation merges material into the documents and empties the inbox",
)
@pytest.mark.anyio
async def test_a_pass_merges_material_and_empties_the_inbox(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    name = _material(body="one fact")
    other = _material(title="Second", body="another fact")

    loop = _Loop(
        [
            (
                "write_document",
                {
                    "title": "Session",
                    "description": "who owns login state",
                    "body": "one fact and more",
                },
            )
        ]
    )
    outcome = await _run(loop, item=Pending(material=name))

    assert outcome["status"] == "ok"
    assert outcome["documents_before"] == 0
    assert outcome["documents_after"] == 1
    assert _documents() == ["shopee/session.md"]
    # The item the pass absorbed left the inbox; the one it was not handed is
    # still owed.
    assert fs.inbox_items("shopee") == (other,)
    # What the pass wrote is stamped, so the sweep does not hand the pass its
    # own output back as an "edit".
    assert fs.read_file("shopee/session.md").curated_at != ""
    assert [p.document for p in pending_items("shopee") if p.document] == []


@pytest.mark.acceptance(
    spec="knowledge", scenario="a document edited out-of-band is curated by the next sweep"
)
@pytest.mark.anyio
async def test_an_edited_document_is_carried_through_then_stamped(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    relpath = _document("Login state", body="the old wording")
    assert pending_items("shopee") == ()

    # A person rewrites it in their own editor: no stamp moves, the mtime does.
    target = paths.resolve(relpath)
    fm_and_body = target.read_text().replace("the old wording", "the corrected wording")
    target.write_text(fm_and_body)
    later = time.time() + 5
    os.utime(target, (later, later))
    assert pending_items("shopee") == (Pending(document=relpath),)

    loop = _Loop([])
    outcome = await _run(loop)

    assert outcome["status"] == "ok"
    assert outcome["item"] == relpath
    # The brief says which document a person edited, in full.
    assert f"The document a person edited: {relpath}" in loop.prompt
    assert "the corrected wording" in loop.prompt
    # And once carried through, it is not handed back on the next sweep — nor
    # is the person's wording touched by the stamp.
    assert pending_items("shopee") == ()
    assert "the corrected wording" in fs.read_file(relpath).body


@pytest.mark.acceptance(
    spec="knowledge", scenario="a pass sees candidates and the catalogue, never the inbox"
)
@pytest.mark.anyio
async def test_the_tool_surface_is_fenced_to_the_collection_s_documents(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    name = _material(body="`account.session` owns login state")
    _material(title="Waiting", body="still in the inbox")
    _document("Login state", body="`account.session` is involved somehow")
    _document("Unrelated", body="nothing in common")
    (paths.collection_dir("shopee") / "README.md").write_text("# shopee\n\nAbout it.\n")

    loop = _Loop(
        [
            ("read_document", {"path": f"shopee/.inbox/{name}"}),
            ("read_document", {"path": "shopee/README.md"}),
            ("read_document", {"path": "other/anything.md"}),
            ("list_documents", {}),
        ]
    )
    await _run(loop, item=Pending(material=name))

    assert loop.tool_names == [
        "list_documents",
        "read_document",
        "retire_document",
        "write_document",
    ]
    # The inbox, the README and another collection are all refused.
    assert all("error" in r for r in loop.results[:3])
    listed = [d["path"] for d in loop.results[3]["documents"]]
    assert listed == ["shopee/login-state.md", "shopee/unrelated.md"]

    # The brief carries the material, the catalogue, and the candidate that
    # actually matched — the catalogue so the model can decide none of them fit.
    assert "account.session" in loop.prompt
    assert "shopee/login-state.md" in loop.prompt
    assert "shopee/unrelated.md" in loop.prompt
    # Other waiting material is not in front of this pass.
    assert "still in the inbox" not in loop.prompt


@pytest.mark.acceptance(spec="knowledge", scenario="a pass is bounded to a handful of writes")
@pytest.mark.anyio
async def test_a_pass_stops_at_the_write_bound(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    name = _material()
    attempts = MAX_WRITES_PER_PASS + 3
    loop = _Loop(
        [
            ("write_document", {"title": f"Doc {n}", "description": "d", "body": f"body {n}"})
            for n in range(attempts)
        ]
    )
    outcome = await _run(loop, item=Pending(material=name))

    assert outcome["written"] == MAX_WRITES_PER_PASS
    refused = [r for r in loop.results if "error" in r]
    assert len(refused) == attempts - MAX_WRITES_PER_PASS
    assert str(MAX_WRITES_PER_PASS) in refused[0]["error"]
    # What did land is whole files, not truncated ones.
    written = catalogue.walk_files(paths.collection_dir("shopee"))
    assert len(written) == MAX_WRITES_PER_PASS
    assert all(fs.read_file(f.path).body.strip().startswith("body") for f in written)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("folder", "expected"),
    [
        ("", "shopee/doc.md"),
        ("account", "shopee/account/doc.md"),
        ("shopee", "shopee/doc.md"),
        ("shopee/account", "shopee/account/doc.md"),
        ("/account/", "shopee/account/doc.md"),
    ],
)
async def test_a_folder_lands_inside_the_collection_however_it_is_spelled(
    knowledge_root, folder: str, expected: str
) -> None:  # type: ignore[no-untyped-def]
    # A model shown paths like `shopee/x.md` answers with `folder="shopee"`,
    # which would produce `shopee/shopee/x.md`. The prefix this layer adds is
    # stripped rather than the spelling being refused.
    name = _material()
    loop = _Loop(
        [("write_document", {"folder": folder, "title": "Doc", "description": "d", "body": "b"})]
    )
    await _run(loop, item=Pending(material=name))
    assert loop.results[0]["path"] == expected


# ----- the reference rule --------------------------------------------------


@pytest.mark.acceptance(
    spec="knowledge", scenario="a curated document carries no file-name reference"
)
@pytest.mark.anyio
async def test_a_write_naming_a_knowledge_file_is_refused(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    name = _material()
    _document("Login state")

    loop = _Loop(
        [
            (
                "write_document",
                {"title": "Session", "description": "d", "body": "see `login-state.md` for more"},
            ),
            (
                "write_document",
                {
                    "title": "Session",
                    "description": "d",
                    "body": "the login-state document covers it",
                },
            ),
        ]
    )
    await _run(loop, item=Pending(material=name))

    assert "error" in loop.results[0] and "login-state.md" in loop.results[0]["error"]
    # The rewrite that names the subject instead of the file goes through.
    assert loop.results[1].get("ok") is True


def test_only_this_corpus_s_file_names_are_refused() -> None:
    known = frozenset({"login-state.md"})
    # A document about a repository may legitimately mention that repository's
    # own files; refusing that would be a rule the model cannot satisfy.
    assert offending_reference("the repo's `AGENTS.md` says so", known, collection="shopee") is None
    # A repository of its own may hold a folder of the same name; that is not
    # this corpus.
    assert offending_reference("see `docs/shopee/overview.md`", known, collection="shopee") is None
    assert (
        offending_reference("see `login-state.md`", known, collection="shopee") == "login-state.md"
    )
    # A path into THIS collection is this corpus by construction.
    assert (
        offending_reference("shopee/anything.md", known, collection="shopee")
        == "shopee/anything.md"
    )


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="the pass is instructed that newer material wins and a person's edit stands",
)
def test_the_system_prompt_states_the_contradiction_and_edit_rules() -> None:
    # No code can adjudicate a contradiction or tell a deliberate edit from a
    # mistake, so the instructions are the whole of "Let newer statements win
    # and a person's edit stand", and this pins them.
    lowered = CURATION_SYSTEM.lower()
    assert "the newer statement wins" in lowered
    assert "previously recorded" in lowered
    assert "corrected" in lowered
    assert "a person's edit is deliberate" in lowered
    assert "never revert" in lowered
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
    assert "retire_document" in tools


def _retire_tools(**kwargs: Any) -> dict[str, Any]:
    return {
        t.name: t
        for t in build_tools(
            service=_service(), collection="shopee", actor="system", counters=Counters(), **kwargs
        )
    }


@pytest.mark.anyio
@pytest.mark.acceptance(
    spec="knowledge", scenario="refuse a retire before the pass has written anything"
)
async def test_a_retire_before_the_pass_has_written_anything_is_refused(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    # "Preserve every fact a pass is shown": a document may be retired only
    # once this pass has written its content somewhere else.
    first = _document("First", body="one fact")
    _document("Second", body="another fact")
    tools = _retire_tools()
    await tools["read_document"].handler({"path": first})

    outcome = await tools["retire_document"].handler({"path": first})

    assert "error" in outcome
    assert "retire" in outcome["error"]
    assert first in _documents()


@pytest.mark.anyio
async def test_a_retire_needs_a_write_elsewhere_after_the_document_was_seen(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    unseen = _document("Unseen", body="a fact nobody read")
    keeper = _document("Keeper", body="k")
    tools = _retire_tools()

    # Writing the document itself is not writing its content elsewhere.
    await tools["write_document"].handler(
        {"path": unseen, "title": "Unseen", "description": "d", "body": "a fact nobody read"}
    )
    refused = await tools["retire_document"].handler({"path": unseen})
    assert "error" in refused
    assert unseen in _documents()

    # A write elsewhere that comes before the pass saw a document does not
    # carry that document's content.
    other = _document("Other", body="o")
    await tools["write_document"].handler(
        {"path": keeper, "title": "Keeper", "description": "d", "body": "k"}
    )
    await tools["read_document"].handler({"path": other})
    refused = await tools["retire_document"].handler({"path": other})
    assert "error" in refused
    assert other in _documents()

    # Read, then written elsewhere: now the retire is allowed.
    await tools["write_document"].handler(
        {"path": keeper, "title": "Keeper", "description": "d", "body": "k and o"}
    )
    retired = await tools["retire_document"].handler({"path": other})
    assert retired == {"ok": True, "path": other}
    assert other not in _documents()


@pytest.mark.anyio
async def test_a_document_shown_in_the_brief_counts_as_seen(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    # The item and the candidates arrive in full in the brief, so the pass has
    # their content without calling read_document.
    shown = _document("Shown", body="s")
    keeper = _document("Keeper", body="k")
    tools = _retire_tools(shown=(shown,))
    await tools["write_document"].handler(
        {"path": keeper, "title": "Keeper", "description": "d", "body": "k and s"}
    )
    assert await tools["retire_document"].handler({"path": shown}) == {
        "ok": True,
        "path": shown,
    }


@pytest.mark.anyio
async def test_a_pass_that_retires_its_own_edited_document_settles_cleanly(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    # An edited document that duplicates another is folded in and retired by
    # the pass; there is then nothing left to stamp, and that is not a failure.
    relpath = fs.write_file(directory="shopee", title="Dup", description="d", body="x").path
    keeper = _document("Keeper", body="x and more")
    loop = _Loop(
        [
            ("read_document", {"path": keeper}),
            (
                "write_document",
                {"path": keeper, "title": "Keeper", "description": "d", "body": "x"},
            ),
            ("retire_document", {"path": relpath}),
        ]
    )
    outcome = await _run(loop, item=Pending(document=relpath))
    assert outcome["status"] == "ok"
    assert _documents() == [keeper]
    assert pending_items("shopee") == ()


async def test_every_turn_of_the_loop_carries_the_operators_bound() -> None:
    """Curation's turns were the one model call in Coffer with no bound at all.

    A wedged endpoint therefore held the pass until the daemon restarted, and
    nothing on any surface said so. The bound travels to the CLIENT rather than
    around the call because the loop is one ``await`` from out here — wrapping
    it could bound the whole conversation or nothing, and neither is "each turn
    gets a fair chance and then gives up".
    """
    _material()
    loop = _Loop([])

    async def chosen() -> int | None:
        return 150

    await _run(loop, read_timeout=chosen)

    assert loop.timeout == 150.0


async def test_a_pass_with_no_settings_to_consult_still_has_a_bound() -> None:
    # The unit-test construction, and any pass built before the singleton
    # exists. Making the bound configurable must not make it optional.
    _material()
    loop = _Loop([])

    await _run(loop)

    assert loop.timeout == DEFAULT_MODEL_TIMEOUT_S


@pytest.mark.anyio
async def test_a_named_document_must_belong_to_the_collection(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    fs.create_collection_dir("other")
    elsewhere = fs.write_file(directory="other", title="Theirs", description="d", body="b").path
    with pytest.raises(UnsafeKnowledgePath):
        await _run(_Loop([]), item=Pending(document=elsewhere))
    with pytest.raises(UnsafeKnowledgePath):
        await _run(_Loop([]), item=Pending(document="shopee/README.md"))
    assert fs.read_file(elsewhere).curated_at == ""
