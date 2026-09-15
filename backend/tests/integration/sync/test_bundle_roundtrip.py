"""The bundle, written and read back one path at a time (spec vault-sync).

Two halves of the converge round, tested without git between them.

**Export** (:class:`SyncExporter` over :class:`Bundle`) serializes a whole vault
into the working tree. What matters is not only *that* the documents appear but
*how*: byte-identically on every export, differentially on every re-export, and
never over a path this vault has not absorbed. Those three are the safety
argument for calling an absence a deletion, so each has a test of its own.

**Apply** (the four appliers) puts one path's change back into a vault, reading
out of that same working tree. Each applier owns a prefix and has exactly two
operations, and the interesting behaviour is at the edges: a gate that refuses
before anything is written, a removal of something already gone, an area no
module claims, a credential blob that arrives older than the one in the vault.

Everything is under ``tmp_path`` — separate SQLite files, separate homes,
separate knowledge and skill trees — and the mirrored-tree roots are pinned, so
nothing here can reach the developer's real ``~/.coffer``.
"""

from __future__ import annotations

import json
import os
import pathlib
import time
from datetime import date
from typing import Any

import pytest
import yaml
from cryptography.fernet import Fernet

from coffer.application.sync.appliers import (
    CredentialApplier,
    ResourceApplier,
    StateApplier,
    TreeApplier,
)
from coffer.domain.resource import ResourceRef
from coffer.domain.scope import Scope
from coffer.domain.sync.errors import SyncSerializationError
from coffer.domain.sync.fernet_time import is_fresher
from coffer.domain.sync.machine import MachineDescriptor
from coffer.domain.sync.manifest import Manifest
from coffer.domain.sync.models import ExportSummary
from tests.integration.sync.harness import (
    MACHINE_A,
    MACHINE_B,
    GateRefusedError,
    VaultMachine,
    build_machine,
)

pytestmark = pytest.mark.timeout(60)


@pytest.fixture(autouse=True)
def _pinned_tree_roots(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let ``paths.mirrored_trees()`` fall back to the real ``~/.coffer``.

    Every ``Bundle`` here is built with explicit ``trees``, so this override is
    a belt-and-braces guard rather than a load-bearing fixture: a future test
    that forgets the argument would otherwise mirror — and converge deletions
    onto — the developer's live vault.
    """
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "roots" / "knowledge"))
    monkeypatch.setenv("COFFER_SKILLS_ROOT", str(tmp_path / "roots" / "skills"))


@pytest.fixture
async def vault(tmp_path: pathlib.Path):
    """One whole vault whose bundle directory is its own working tree.

    The remote URL is never reached: no test in this file converges, so no git
    binary runs. The bundle is simply a directory on disk, which is exactly
    what the export writes and what the appliers read.
    """
    machine = await build_machine(
        name="laptop",
        machine_id=MACHINE_A,
        root=tmp_path / "vault",
        remote_url=str(tmp_path / "unused-remote.git"),
    )
    yield machine
    await machine.close()


# --- helpers ---------------------------------------------------------------


def _areas(summary: ExportSummary) -> dict[str, int]:
    return {a.area: a.count for a in summary.areas}


def _age(root: pathlib.Path) -> None:
    """Stamp every file well into the past, so "was it rewritten?" cannot be
    answered wrongly by two writes landing in the same clock tick."""
    for path in root.rglob("*"):
        if path.is_file():
            os.utime(path, (1_000_000_000, 1_000_000_000))


def _mtimes(root: pathlib.Path) -> dict[str, int]:
    """Every bundle file's mtime except the manifest's.

    The manifest is rewritten on every export by design (its bytes are
    constant, which is the property the determinism test asserts); its mtime
    therefore says nothing about whether an area was needlessly rewritten.
    """
    return {
        p.relative_to(root).as_posix(): p.stat().st_mtime_ns
        for p in root.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    }


def _bytes(root: pathlib.Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _doc(path: pathlib.Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), f"{path} is not a mapping"
    return loaded


def _stage(worktree: pathlib.Path, rel: str, payload: str | bytes) -> pathlib.Path:
    """Put a file into the working tree the way a merge would have."""
    target = worktree / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, bytes):
        target.write_bytes(payload)
    else:
        target.write_text(payload, encoding="utf-8")
    return target


def _stage_doc(worktree: pathlib.Path, rel: str, doc: dict[str, Any]) -> pathlib.Path:
    return _stage(worktree, rel, yaml.safe_dump(doc, sort_keys=True, allow_unicode=True))


async def _populate(machine: VaultMachine) -> None:
    """A vault with something in every area the export serializes."""
    await machine.register("mcp_server", "files", {"value": "files"})
    await machine.register("agent", "coder", {"value": "coder"})
    machine.write_knowledge("notes", "alpha", "alpha body\n")
    machine.write_knowledge("notes", "beta", "beta body\n")
    machine.write_skill("demo", "# demo skill\n")
    machine.state_provider.docs["peer-1"] = {"paired": True}
    machine.set_credential("mcp/files/token", "s3cret")


# --- export ----------------------------------------------------------------


async def test_export_writes_every_area_and_counts_it(vault: VaultMachine) -> None:
    await _populate(vault)

    summary = await vault.exporter.export(vault.bundle, with_credentials=False)
    root = pathlib.Path(vault.bundle.path)

    manifest = Manifest.from_dict(json.loads((root / "manifest.json").read_text("utf-8")))
    assert manifest.schema_version == 1
    # A converge export writes no creation time: a restamped timestamp would
    # stage a change on every round.
    assert manifest.created_at is None

    files = _doc(root / "resources" / "mcp_server" / "files.yaml")
    assert files == {
        "kind": "mcp_server",
        "name": "files",
        "description": None,
        "config": {"value": "files", "config_dir": "", "credential_ref": ""},
    }
    assert (root / "resources" / "agent" / "coder.yaml").is_file()

    assert (root / "knowledge" / "notes" / "alpha.md").read_text(encoding="utf-8") == "alpha body\n"
    assert (root / "knowledge" / "notes" / "beta.md").is_file()
    assert (root / "skills" / "demo" / "SKILL.md").read_text(encoding="utf-8") == "# demo skill\n"
    assert _doc(root / "state" / "peers" / "peer-1.yaml") == {"paired": True}

    # Opt-in: the vault holds a credential and the bundle carries no trace.
    assert not (root / "credentials").exists()
    assert summary.credentials_included is False

    assert _areas(summary) == {
        "resources": 2,
        "knowledge": 2,
        "skills": 1,
        "state/peers": 1,
    }
    assert summary.path == str(root)
    assert summary.failures == []


async def test_export_leaves_reach_behind(vault: VaultMachine) -> None:
    """The document is the resource, not the user's answer about it.

    ``enabled`` and ``scope`` read like two fields and are one thing — how far
    this resource reaches — and it is set per machine. A document that carried
    it would let the machine that exported last silently re-answer, every
    round, a question the other machine had already answered for itself.
    """
    await vault.register("mcp_server", "files", {"value": "files"})
    await vault.set_enabled("mcp_server", "files", False)
    await vault.set_scope("mcp_server", "files", Scope(agents=["codex"]))

    await vault.exporter.export(vault.bundle, with_credentials=False)

    path = pathlib.Path(vault.bundle.path) / "resources" / "mcp_server" / "files.yaml"
    assert set(_doc(path)) == {"kind", "name", "description", "config"}
    # Not merely absent as keys — absent as text, so a future encoder cannot
    # smuggle either back in under a nested name.
    raw = path.read_text(encoding="utf-8")
    assert "enabled" not in raw
    assert "scope" not in raw


async def test_export_writes_a_channel_document_like_any_other(vault: VaultMachine) -> None:
    """A channel is exported now, and counted as exported.

    It used to be withheld entirely, on the grounds that an inbound surface
    means nothing off its host. The document travels because it names the one
    machine whose daemon runs its adapter, and the binding must be in the
    document for that to be worth anything — a document that travelled without
    it would be a channel every machine could read as its own.
    """
    await vault.register("mcp_server", "files", {"value": "files"})
    await vault.register("channel", "seatalk", {"value": "port-8787", "runs_on": vault.machine_id})

    summary = await vault.exporter.export(vault.bundle, with_credentials=False)

    root = pathlib.Path(vault.bundle.path)
    document = root / "resources" / "channel" / "seatalk.yaml"
    assert document.is_file()
    assert _doc(document)["config"]["runs_on"] == vault.machine_id
    assert _areas(summary)["resources"] == 2
    assert summary.failures == []


async def test_a_second_export_of_an_unchanged_vault_is_identical_and_rewrites_nothing(
    vault: VaultMachine,
) -> None:
    await _populate(vault)
    root = pathlib.Path(vault.bundle.path)

    await vault.exporter.export(vault.bundle, with_credentials=True)
    _age(root)
    before_mtimes, before_bytes = _mtimes(root), _bytes(root)
    assert before_mtimes, "the bundle really does hold documents to leave alone"

    await vault.exporter.export(vault.bundle, with_credentials=True)

    # Byte-identical (spec vault-sync "Determinism and path portability") — the
    # manifest included, which is why it can be rewritten harmlessly.
    assert _bytes(root) == before_bytes
    # And not one document was touched: an idle vault stages nothing, so a
    # round with nothing to say produces no commit.
    assert _mtimes(root) == before_mtimes


async def test_a_locally_deleted_resource_removes_exactly_its_document(
    vault: VaultMachine,
) -> None:
    await _populate(vault)
    await vault.register("mcp_server", "gone", {"value": "gone"})
    root = pathlib.Path(vault.bundle.path)

    await vault.exporter.export(vault.bundle, with_credentials=True)
    _age(root)
    before = _mtimes(root)
    gone = "resources/mcp_server/gone.yaml"
    assert gone in before

    await vault.resources.delete(ResourceRef("mcp_server", "gone"), "test")
    await vault.exporter.export(vault.bundle, with_credentials=True)

    # Exactly one document disappeared, and every other file kept the mtime it
    # had: the export diffs, it does not clear and rewrite the directory.
    assert _mtimes(root) == {rel: at for rel, at in before.items() if rel != gone}
    assert (root / "resources" / "mcp_server" / "files.yaml").is_file()


async def test_an_export_never_deletes_a_path_this_vault_has_not_absorbed(
    vault: VaultMachine,
) -> None:
    await _populate(vault)
    root = pathlib.Path(vault.bundle.path)
    await vault.exporter.export(vault.bundle, with_credentials=True)

    # What a merge leaves behind when this vault could not apply the other
    # machine's documents: files in the tree that local state does not produce.
    pending = {
        "resources/mcp_server/theirs.yaml": yaml.safe_dump(
            {"kind": "mcp_server", "name": "theirs", "config": {"value": "b"}},
            sort_keys=True,
        ),
        "state/peers/peer-2.yaml": yaml.safe_dump({"paired": False}, sort_keys=True),
        "credentials/mcp/other/token.enc": "gAAAAA-not-ours",
        "knowledge/theirs/note.md": "not absorbed\n",
        "skills/theirs/SKILL.md": "# not absorbed\n",
    }
    for rel, payload in pending.items():
        _stage(root, rel, payload)

    for rel in pending:
        await vault.state.hold(rel, applicable=True)
    await vault.exporter.export(vault.bundle, with_credentials=True)

    for rel, payload in pending.items():
        assert (root / rel).read_text(encoding="utf-8") == payload, (
            f"{rel} was pending, not deleted"
        )
    # The vault's own documents are still there too.
    assert (root / "knowledge" / "notes" / "alpha.md").is_file()
    assert (root / "resources" / "mcp_server" / "files.yaml").is_file()

    # And the hold is what saved them: released, the same export removes them.
    for rel in pending:
        await vault.state.release(rel)
    await vault.exporter.export(vault.bundle, with_credentials=True)

    for rel in pending:
        assert not (root / rel).exists(), rel
    assert (root / "knowledge" / "notes" / "alpha.md").is_file()
    assert (root / "skills" / "demo" / "SKILL.md").is_file()


async def test_credentials_are_opt_in_and_the_master_key_never_enters_the_bundle(
    vault: VaultMachine,
) -> None:
    await _populate(vault)
    root = pathlib.Path(vault.bundle.path)
    key = vault.master_key.export_key()
    assert key is not None

    without = await vault.exporter.export(vault.bundle, with_credentials=False)
    assert not (root / "credentials").exists()
    assert "credentials" not in _areas(without)

    summary = await vault.exporter.export(vault.bundle, with_credentials=True)
    assert summary.credentials_included is True
    assert _areas(summary)["credentials"] == 1

    blob = (root / "credentials" / "mcp" / "files" / "token.enc").read_bytes()
    # Ciphertext, and the exact ciphertext the vault holds.
    assert blob == vault.credentials.read_ciphertext("mcp/files/token")
    assert Fernet(key).decrypt(blob) == b"s3cret"

    listed = vault.bundle.list_files()
    assert "credentials/mcp/files/token.enc" in {p.replace(os.sep, "/") for p in listed}
    for rel in listed:
        payload = (root / rel).read_bytes()
        assert key not in payload, rel
        assert b"s3cret" not in payload, rel


async def test_home_paths_leave_the_vault_as_a_portable_token(vault: VaultMachine) -> None:
    home = str(vault.home)
    await vault.register(
        "agent",
        "coder",
        {"config_dir": f"{home}/.claude", "value": "/opt/shared/bin"},
    )
    root = pathlib.Path(vault.bundle.path)

    await vault.exporter.export(vault.bundle, with_credentials=False)

    config = _doc(root / "resources" / "agent" / "coder.yaml")["config"]
    assert config["config_dir"] == "${HOME}/.claude"
    # A path outside $HOME rides verbatim rather than being mangled.
    assert config["value"] == "/opt/shared/bin"
    assert home not in (root / "resources" / "agent" / "coder.yaml").read_text(encoding="utf-8")


async def test_a_machine_publishes_its_own_descriptor_and_no_other(vault: VaultMachine) -> None:
    await _populate(vault)
    await vault.register("agent", "writer", {"value": "writer"})
    root = pathlib.Path(vault.bundle.path)
    today = date(2026, 9, 13)
    await vault.exporter.export(vault.bundle, with_credentials=True)

    theirs = MachineDescriptor(
        machine_id=MACHINE_B,
        name="desktop",
        os="linux",
        hostname="thinkpad",
        coffer_version="0.6.0",
    )
    vault.bundle.write_machine_descriptor(MACHINE_B, theirs.to_doc())
    await vault.registry.publish_self(vault.bundle, commit="abc1234", today=today)

    read = vault.bundle.read_machine_descriptors()
    assert set(read) == {MACHINE_A, MACHINE_B}
    assert MachineDescriptor.from_doc(MACHINE_B, read[MACHINE_B]) == theirs

    mine = MachineDescriptor.from_doc(MACHINE_A, read[MACHINE_A])
    assert mine.name == "laptop"
    assert mine.last_converged_on == today
    assert mine.last_converged_commit == "abc1234"
    assert mine.key_fingerprint == vault.key_fingerprint()
    assert mine.agents == ("coder", "writer")

    _age(root)
    stamps = _mtimes(root)

    # A whole export plus a second publish on the same day: every other area
    # converges against local state, and none of them may sweep the registry.
    await vault.exporter.export(vault.bundle, with_credentials=True)
    await vault.registry.publish_self(vault.bundle, commit="abc1234", today=today)

    assert _mtimes(root) == stamps
    assert set(vault.bundle.read_machine_descriptors()) == {MACHINE_A, MACHINE_B}

    # An id is a filename; it may never name a path.
    with pytest.raises(ValueError):
        vault.bundle.write_machine_descriptor("../escape", theirs.to_doc())


# --- apply: knowledge/ and skills/ -----------------------------------------


async def test_tree_applier_copies_files_in_and_prunes_emptied_collections(
    vault: VaultMachine,
) -> None:
    applier = TreeApplier("knowledge/", worktree=vault.worktree, live_root=vault.knowledge_root)
    _stage(vault.worktree, "knowledge/notes/alpha.md", "alpha body\n")
    _stage(vault.worktree, "knowledge/notes/deep/beta.md", "beta body\n")

    await applier.upsert("knowledge/notes/alpha.md")
    await applier.upsert("knowledge/notes/deep/beta.md")
    assert vault.read_knowledge("notes", "alpha") == "alpha body\n"
    assert vault.knowledge_paths() == {"notes/alpha.md", "notes/deep/beta.md"}

    await applier.remove("knowledge/notes/deep/beta.md")
    # The emptied sub-collection is gone; the one still holding a note is not.
    assert not (vault.knowledge_root / "notes" / "deep").exists()
    assert (vault.knowledge_root / "notes").is_dir()

    await applier.remove("knowledge/notes/alpha.md")
    assert vault.knowledge_paths() == set()
    assert not (vault.knowledge_root / "notes").exists()
    # The root itself survives: it is the tree, not a collection in it.
    assert vault.knowledge_root.is_dir()


async def test_tree_applier_also_carries_the_skill_store(vault: VaultMachine) -> None:
    applier = TreeApplier("skills/", worktree=vault.worktree, live_root=vault.skills_root)
    _stage(vault.worktree, "skills/demo/SKILL.md", "# demo\n")

    await applier.upsert("skills/demo/SKILL.md")
    assert vault.has_skill_files("demo")
    assert (vault.skills_root / "demo" / "SKILL.md").read_text(encoding="utf-8") == "# demo\n"

    await applier.remove("skills/demo/SKILL.md")
    assert not vault.has_skill_files("demo")
    assert not (vault.skills_root / "demo").exists()


async def test_tree_applier_refuses_a_symlink_in_the_working_tree(vault: VaultMachine) -> None:
    """A link committed on another machine points at something on *this* one.
    Following it would read that file into the vault, so it is refused."""
    applier = TreeApplier("knowledge/", worktree=vault.worktree, live_root=vault.knowledge_root)
    outside = vault.root / "outside.txt"
    outside.write_text("not vault content\n", encoding="utf-8")
    (vault.worktree / "knowledge" / "notes").mkdir(parents=True)
    (vault.worktree / "knowledge" / "notes" / "link.md").symlink_to(outside)

    with pytest.raises(SyncSerializationError) as refused:
        await applier.upsert("knowledge/notes/link.md")

    assert "symlink" in str(refused.value)
    assert vault.knowledge_paths() == set()


async def test_tree_applier_refuses_a_path_that_is_not_a_file(vault: VaultMachine) -> None:
    applier = TreeApplier("knowledge/", worktree=vault.worktree, live_root=vault.knowledge_root)
    (vault.worktree / "knowledge" / "notes").mkdir(parents=True)

    with pytest.raises(SyncSerializationError) as missing:
        await applier.upsert("knowledge/notes/absent.md")
    assert "knowledge/notes/absent.md" in str(missing.value)

    with pytest.raises(SyncSerializationError):
        await applier.upsert("knowledge/notes")

    assert vault.knowledge_paths() == set()


# --- apply: resources/ ------------------------------------------------------


async def test_resource_applier_registers_then_updates_a_row(vault: VaultMachine) -> None:
    applier = ResourceApplier(
        vault.resources, worktree=vault.worktree, gates=[], home=str(vault.home)
    )
    path = "resources/mcp_server/files.yaml"
    _stage_doc(
        vault.worktree,
        path,
        {
            "kind": "mcp_server",
            "name": "files",
            "description": "the file server",
            "config": {"value": "first", "config_dir": "${HOME}/.files"},
        },
    )

    await applier.upsert(path)
    created = await vault.resources.get(ResourceRef("mcp_server", "files"))
    assert created.description == "the file server"
    assert created.config["value"] == "first"
    # ``${HOME}`` expands against THIS machine's home, not the exporter's.
    assert created.config["config_dir"] == f"{vault.home}/.files"
    # A row nobody here has looked at yet gets this machine's own default
    # reach, because nobody here has answered that question for it.
    assert created.enabled is True
    assert created.scope is None

    # What the user does next is the reach decision, made here.
    await vault.set_enabled("mcp_server", "files", False)
    await vault.set_scope("mcp_server", "files", Scope(agents=["claude-code"]))

    _stage_doc(
        vault.worktree,
        path,
        {
            "kind": "mcp_server",
            "name": "files",
            "description": "renamed in the doc",
            "config": {"value": "second", "config_dir": "${HOME}/elsewhere"},
        },
    )
    await applier.upsert(path)

    updated = await vault.resources.get(ResourceRef("mcp_server", "files"))
    assert updated.id == created.id, "the row was updated, not replaced"
    assert updated.description == "renamed in the doc"
    assert updated.config["value"] == "second"
    assert updated.config["config_dir"] == f"{vault.home}/elsewhere"
    # The update carried config and description and revised no reach: the
    # answer this machine gave a moment ago is still the answer.
    assert updated.enabled is False
    assert updated.scope == Scope(agents=["claude-code"])
    assert await vault.resource_names("mcp_server") == ["files"]


async def test_resource_applier_takes_an_older_builds_document_without_its_reach(
    vault: VaultMachine,
) -> None:
    """The shared tree still holds documents written before reach stopped
    travelling, and machines that have not upgraded keep writing more.

    Such a document must import — refusing it the way an unknown field is
    refused would quarantine it on every upgraded machine, so one stale machine
    would stall the fleet — and what it says about reach must go nowhere.
    """
    applier = ResourceApplier(
        vault.resources, worktree=vault.worktree, gates=[], home=str(vault.home)
    )
    await vault.register("mcp_server", "files", {"value": "local"})
    await vault.set_enabled("mcp_server", "files", False)
    await vault.set_scope("mcp_server", "files", Scope(agents=["claude-code"]))

    path = "resources/mcp_server/files.yaml"
    _stage_doc(
        vault.worktree,
        path,
        {
            "kind": "mcp_server",
            "name": "files",
            "description": None,
            "enabled": True,
            "config": {"value": "from-the-old-build"},
            "scope": {"agents": [], "machines": [MACHINE_B]},
        },
    )

    await applier.upsert(path)

    got = await vault.resources.get(ResourceRef("mcp_server", "files"))
    assert got.config["value"] == "from-the-old-build", "the document must still import"
    # Neither half of the reach it carried — not the ``enabled: true`` that
    # would have switched this server back on, nor the two scope axes, one of
    # which names a machine this build has no field for.
    assert got.enabled is False
    assert got.scope == Scope(agents=["claude-code"])


async def test_bundle_reads_an_older_builds_document_but_not_a_misspelled_one(
    vault: VaultMachine,
) -> None:
    """The same leniency at the seam that validates a whole document.

    ``Bundle.read_resource_docs`` is where a document is parsed rather than
    merely read key by key, so it is where "tolerate the two retired reach
    fields, refuse anything else" is decidable. Tolerated means *dropped*: the
    parsed document has no field left to carry reach in.
    """
    root = pathlib.Path(vault.bundle.path)
    _stage_doc(
        root,
        "resources/mcp_server/old.yaml",
        {
            "kind": "mcp_server",
            "name": "old",
            "description": None,
            "enabled": False,
            "config": {"value": "v"},
            "scope": {"agents": [], "machines": [MACHINE_B]},
        },
    )

    docs = vault.bundle.read_resource_docs()

    assert [(d.kind, d.name, d.config) for d in docs] == [("mcp_server", "old", {"value": "v"})]
    assert not hasattr(docs[0], "enabled")
    assert not hasattr(docs[0], "scope")

    # And a typo'd key is still a document that would import as something
    # other than what it says.
    _stage_doc(
        root,
        "resources/mcp_server/typo.yaml",
        {"kind": "mcp_server", "name": "typo", "description": None, "config": {}, "scop": None},
    )
    with pytest.raises(SyncSerializationError):
        vault.bundle.read_resource_docs()


async def test_resource_applier_runs_the_gate_before_it_writes_anything(
    vault: VaultMachine,
) -> None:
    vault.gate.refuse_value = "nope"
    applier = ResourceApplier(
        vault.resources, worktree=vault.worktree, gates=[vault.gate], home=str(vault.home)
    )
    path = "resources/mcp_server/blocked.yaml"
    _stage_doc(
        vault.worktree,
        path,
        {
            "kind": "mcp_server",
            "name": "blocked",
            "config": {"value": "nope", "config_dir": "${HOME}/.gone"},
        },
    )

    with pytest.raises(GateRefusedError):
        await applier.upsert(path)

    # Nothing was written: the refusal is reported, not half-applied.
    assert await vault.find("mcp_server", "blocked") is None
    assert await vault.resource_names("mcp_server") == []

    # And the gate judged this machine's view of the document — the expanded
    # config — rather than the portable form on disk. It is handed the config
    # and nothing else: reach does not travel, so there is no scope to pass.
    assert vault.gate.seen == [{"value": "nope", "config_dir": f"{vault.home}/.gone"}]


# --- apply: a channel is an ordinary document now ---------------------------


async def test_resource_applier_registers_an_arriving_channel_with_its_binding(
    vault: VaultMachine,
) -> None:
    """The document lands, and it lands naming somebody else's machine.

    That is the whole of what the apply side owes: register the channel as it
    was written, binding included. What stops this machine from answering the
    bot is not the applier refusing the row — it is the runtime reading a name
    that is not its own.
    """
    applier = ResourceApplier(
        vault.resources, worktree=vault.worktree, gates=[], home=str(vault.home)
    )
    _stage_doc(
        vault.worktree,
        "resources/channel/theirs.yaml",
        {
            "kind": "channel",
            "name": "theirs",
            "description": None,
            "config": {"value": "their-port-8787", "runs_on": "ffffffffffffffff"},
        },
    )

    await applier.upsert("resources/channel/theirs.yaml")

    arrived = await vault.find("channel", "theirs")
    assert arrived is not None
    assert arrived.config["runs_on"] == "ffffffffffffffff"


async def test_a_channel_deletion_in_the_tree_deletes_the_channel(
    vault: VaultMachine,
) -> None:
    """A channel deletion is honoured like every other kind's.

    It was once refused outright, and that refusal was a safety property rather
    than tidiness: the build that stopped exporting channels published every
    channel document already in the tree as a deletion, and honouring those
    would have walked each machine's own channels out of its registry. That
    build is behind us — a channel is exported again — so the refusal would now
    only mean a channel the user deleted on one machine coming back on the
    other. The one-way upgrade ordering it leaves behind is written down in
    spec vault-sync's amendment, not papered over here.
    """
    applier = ResourceApplier(
        vault.resources, worktree=vault.worktree, gates=[], home=str(vault.home)
    )
    await vault.register("channel", "seatalk", {"value": "port-8787", "runs_on": vault.machine_id})
    _stage_doc(
        vault.worktree,
        "resources/channel/seatalk.yaml",
        {
            "kind": "channel",
            "name": "seatalk",
            "description": None,
            "config": {"value": "port-8787", "runs_on": vault.machine_id},
        },
    )

    await applier.remove("resources/channel/seatalk.yaml")

    assert await vault.find("channel", "seatalk") is None


async def test_resource_applier_removes_a_row_and_agrees_when_it_is_already_gone(
    vault: VaultMachine,
) -> None:
    applier = ResourceApplier(
        vault.resources, worktree=vault.worktree, gates=[], home=str(vault.home)
    )
    await vault.register("mcp_server", "files", {"value": "files"})
    await vault.register("mcp_server", "keep", {"value": "keep"})

    await applier.remove("resources/mcp_server/files.yaml")
    assert await vault.resource_names("mcp_server") == ["keep"]

    # Two machines deleting the same resource is agreement, not failure.
    await applier.remove("resources/mcp_server/files.yaml")
    assert await vault.resource_names("mcp_server") == ["keep"]


# --- apply: state/ ----------------------------------------------------------


async def test_state_applier_routes_to_the_provider_that_claims_the_area(
    vault: VaultMachine,
) -> None:
    applier = StateApplier([vault.state_provider], worktree=vault.worktree)
    _stage_doc(vault.worktree, "state/peers/peer-1.yaml", {"paired": True, "alias": "x"})
    _stage_doc(vault.worktree, "state/peers/team/alpha.yaml", {"paired": False})

    await applier.upsert("state/peers/peer-1.yaml")
    await applier.upsert("state/peers/team/alpha.yaml")
    assert vault.state_provider.docs == {
        "peer-1": {"paired": True, "alias": "x"},
        "team/alpha": {"paired": False},
    }

    await applier.remove("state/peers/peer-1.yaml")
    assert vault.state_provider.docs == {"team/alpha": {"paired": False}}


async def test_state_docs_carry_home_as_a_sentinel_both_ways(vault: VaultMachine) -> None:
    """spec vault-sync ``## Determinism and path portability``: the ``${HOME}``
    rule is one rule for every serialized document, state areas included."""
    home = str(vault.home)
    vault.state_provider.docs["peer-1"] = {"log": f"{home}/logs/peer-1.log", "paired": True}

    await vault.exporter.export(vault.bundle, with_credentials=False)
    written = _doc(vault.worktree / "state" / "peers" / "peer-1.yaml")
    assert written == {"log": "${HOME}/logs/peer-1.log", "paired": True}

    # The other machine's home is different, and the sentinel expands to it.
    other_home = str(vault.root / "elsewhere")
    applier = StateApplier([vault.state_provider], worktree=vault.worktree, home=other_home)
    await applier.upsert("state/peers/peer-1.yaml")
    assert vault.state_provider.docs["peer-1"] == {
        "log": f"{other_home}/logs/peer-1.log",
        "paired": True,
    }


async def test_state_applier_skips_an_area_no_module_claims(vault: VaultMachine) -> None:
    applier = StateApplier([vault.state_provider], worktree=vault.worktree)
    vault.state_provider.docs["peer-1"] = {"paired": True}
    _stage_doc(vault.worktree, "state/pairings/x.yaml", {"from": "a newer build"})

    # An area belonging to a module this build does not have is skipped, not
    # failed: refusing it every round would make a version difference a
    # permanent error.
    await applier.upsert("state/pairings/x.yaml")
    await applier.remove("state/pairings/x.yaml")

    assert vault.state_provider.docs == {"peer-1": {"paired": True}}


# --- apply: credentials/ ----------------------------------------------------


async def test_credential_applier_writes_ciphertext_and_refuses_a_staler_blob(
    vault: VaultMachine,
) -> None:
    applier = CredentialApplier(vault.credentials, worktree=vault.worktree)
    key = vault.master_key.export_key()
    assert key is not None
    fernet = Fernet(key)

    # Fernet's cleartext timestamp has one-second resolution, so the two
    # encryptions are placed a minute apart explicitly rather than by sleeping.
    now = int(time.time())
    older = fernet.encrypt_at_time(b"old-secret", now - 60)
    newer = fernet.encrypt_at_time(b"new-secret", now)
    assert is_fresher(newer, older) and not is_fresher(older, newer)

    ref = "mcp/files/token"
    path = f"credentials/{ref}.enc"

    _stage(vault.worktree, path, newer)
    await applier.upsert(path)
    assert vault.credentials.read_ciphertext(ref) == newer
    assert fernet.decrypt(newer) == b"new-secret"

    # A blob that reaches this machine already stale is refused: writing it
    # would orphan a working secret.
    _stage(vault.worktree, path, older)
    await applier.upsert(path)
    assert vault.credentials.read_ciphertext(ref) == newer

    await applier.remove(path)
    assert vault.credentials.read_ciphertext(ref) is None
    assert vault.credentials.list_refs() == []


async def test_credential_applier_accepts_a_fresher_blob(vault: VaultMachine) -> None:
    applier = CredentialApplier(vault.credentials, worktree=vault.worktree)
    key = vault.master_key.export_key()
    assert key is not None
    fernet = Fernet(key)

    now = int(time.time())
    older = fernet.encrypt_at_time(b"old-secret", now - 60)
    newer = fernet.encrypt_at_time(b"new-secret", now)

    ref = "mcp/files/token"
    path = f"credentials/{ref}.enc"
    vault.credentials.write_ciphertext(ref, older)

    _stage(vault.worktree, path, newer)
    await applier.upsert(path)

    assert vault.credentials.read_ciphertext(ref) == newer
    assert fernet.decrypt(vault.credentials.read_ciphertext(ref) or b"") == b"new-secret"
