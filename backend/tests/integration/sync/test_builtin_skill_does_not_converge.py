"""Coffer's own generated skill stays home (spec vault-sync FR-093).

Two whole vaults and one real bare git repository, exactly as the rest of this
directory: nothing below the git binary is faked, because the claim under test
is about what two machines end up holding after they have actually talked.

The defect this file pins down is a loop, not a wrong value. `coffer-guide` is
rendered locally from the running build, the knowledge files (which converge)
and **which collections this machine has enabled** — and reach is deliberately
machine-local (FR-014). So two machines that agree about every file still
render different bytes. While both halves of a skill converged, each round had
one machine overwrite the other's master folder and resource row, the
overwritten machine re-rendered on its next boot or curation tick, and the
whole thing repeated: a commit and an audit event per tick on both machines,
forever, over an artifact neither machine ever reads from the other.

The two texts here are produced by the **real renderer**, from two catalogues
that differ only in which collection is switched on, so the test's premise is
the product's own behaviour rather than a pair of strings chosen to differ.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess

import pytest

from coffer.application.knowledge.guide_render import GUIDE_SKILL_NAME, render
from coffer.domain.knowledge.entry import CollectionEntry, FileEntry
from coffer.domain.sync.convergence import ConvergeStatus
from coffer.domain.sync.manifest import MANIFEST_PATH
from tests.integration.sync.harness import BRANCH, VaultMachine, settle, two_machines

pytestmark = pytest.mark.timeout(120)

GUIDE_TREE_PREFIX = f"skills/{GUIDE_SKILL_NAME}/"
GUIDE_SKILL_MD = f"{GUIDE_TREE_PREFIX}SKILL.md"

# The skills *tree* is still filed under the folder's name, because that is
# what it is — a directory on disk. The resource *document* is not: it lives at
# ``resources/skill/<uid>.yaml`` (ADR resource-identity-is-an-immutable-uid),
# and a uid is minted by whichever machine first seeded the row, so there is no
# module-level constant for it. Ask the machine — ``_guide_doc`` below.

_COLLECTIONS = {
    "notes": ("Day-to-day working notes.", "notes/standup.md", "Standup"),
    "archive": ("Things kept for later.", "archive/old-runbook.md", "Old runbook"),
}


def _guide_text(*enabled: str) -> str:
    """What the guide renders to on a machine with exactly ``enabled`` on.

    The renderer is pure and takes the catalogue it is given, which is the
    whole point: ``KnowledgeService.catalogue()`` builds that list from
    ``enabled_collections()``, so "which collections are switched on here" is
    an input to these bytes.
    """
    catalogue = []
    for name in enabled:
        description, path, title = _COLLECTIONS[name]
        # A uid is required of a catalogue entry now, and deliberately fixed
        # here: the rendered text must depend on WHICH collections are on and
        # on nothing else, so a per-machine identity leaking into these bytes
        # would recreate the very divergence this file is about.
        entry = CollectionEntry(
            uid=f"rsc_{name}",
            name=name,
            description=description,
            document_count=1,
        )
        document = FileEntry(
            path=path, title=title, description=description, actor="agent", updated_at=""
        )
        catalogue.append((entry, [document]))
    return render("~/.coffer/knowledge", catalogue)


def _builtin_config(text: str) -> dict[str, object]:
    """A builtin skill's row as the seed writes it.

    ``version_hash`` is the digest of the master's bytes, which is why the row
    cannot escape the loop on its own: the row differs exactly when the folder
    does.
    """
    return {
        "value": GUIDE_SKILL_NAME,
        "source": {"type": "builtin"},
        "version_hash": hashlib.sha256(text.encode()).hexdigest(),
    }


async def _seed_guide(machine: VaultMachine, text: str) -> None:
    """What a boot does on one machine: write the master, register the row."""
    machine.write_skill(GUIDE_SKILL_NAME, text)
    await machine.register("skill", GUIDE_SKILL_NAME, _builtin_config(text))


async def _guide_doc(machine: VaultMachine) -> str:
    """Where *this* machine's guide document would sit, if it published one.

    Each machine seeds its own guide and mints its own uid for it, so the two
    machines here disagree about this path — which is itself the point: a
    document keyed on identity is one machine's row, not a shared slot two
    machines take turns overwriting.
    """
    return await machine.doc_path("skill", GUIDE_SKILL_NAME)


def _master(machine: VaultMachine) -> str | None:
    path = machine.skills_root / GUIDE_SKILL_NAME / "SKILL.md"
    return path.read_text(encoding="utf-8") if path.is_file() else None


@pytest.fixture
async def pair(tmp_path: pathlib.Path):
    a, b = await two_machines(tmp_path, shared_key=True)
    yield a, b
    await a.close()
    await b.close()


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="a locally generated skill is neither published nor overwritten",
)
async def test_two_machines_keep_their_own_guide_and_stop_talking_about_it(pair) -> None:
    """The loop, set up exactly as it occurred, and then absent.

    A has both collections enabled; B has switched ``archive`` off. The
    knowledge files themselves converge — that is the control, and it has to
    keep working — while the guide rendered from them does not.
    """
    a, b = pair
    text_a = _guide_text("notes", "archive")
    text_b = _guide_text("notes")
    assert text_a != text_b, "the premise: a disabled collection changes the rendered bytes"

    a.write_knowledge("notes", "standup", "what we did\n")
    a.write_knowledge("archive", "old-runbook", "how it used to work\n")
    a.write_skill("imported-skill", "# an ordinary skill a person imported\n")
    await a.register("skill", "imported-skill")
    await _seed_guide(a, text_a)
    await _seed_guide(b, text_b)

    await settle(a, b)

    # 1. Neither machine's manual was overwritten by the other's.
    assert _master(a) == text_a
    assert _master(b) == text_b

    # 2. Neither half of it was published at all — not the folder, not the row.
    remote = await a.remote_paths()
    assert not [p for p in remote if p.startswith(GUIDE_TREE_PREFIX)], sorted(remote)
    for machine in (a, b):
        assert await _guide_doc(machine) not in remote, sorted(remote)

    # 3. The control: everything else still converges, so the silence above is
    #    about this one artifact and not about a round that stopped working.
    assert b.read_knowledge("notes", "standup") == "what we did\n"
    assert b.read_knowledge("archive", "old-runbook") == "how it used to work\n"
    assert b.has_skill_files("imported-skill")
    assert "imported-skill" in await b.resource_names("skill")

    # 4. Each machine still has its own row, untouched by the other.
    for machine in (a, b):
        row = await machine.find("skill", GUIDE_SKILL_NAME)
        assert row is not None
        assert (
            row.config["version_hash"]
            == _builtin_config(text_a if machine is a else text_b)["version_hash"]
        )

    # 5. And the fleet is quiet: another round on each machine publishes
    #    nothing, applies nothing and adds no commit. This is the assertion the
    #    defect fails — before the fix each tick produced one commit per
    #    machine, forever.
    commits = await a.remote_commit_count()
    for machine in (a, b):
        run = await machine.adopt()
        assert run.status is ConvergeStatus.NO_CHANGE, (run.status, run.error)
        assert not run.published.changes
        assert not run.applied.changes
    assert await a.remote_commit_count() == commits
    assert _master(a) == text_a
    assert _master(b) == text_b


async def test_a_second_render_on_one_machine_is_not_news_to_the_other(pair) -> None:
    """The other half of the loop: a re-render publishes nothing either.

    A curation pass moves the catalogue and the master is rewritten in place.
    Before the fix that rewrite was a staged change, a commit, and a diff the
    other machine applied — here it never leaves the machine.
    """
    a, b = pair
    await _seed_guide(a, _guide_text("notes"))
    await _seed_guide(b, _guide_text("notes", "archive"))
    await settle(a, b)

    rewritten = _guide_text("notes", "archive")
    a.write_skill(GUIDE_SKILL_NAME, rewritten)
    await a.edit_config("skill", GUIDE_SKILL_NAME, _builtin_config(rewritten))

    run = await a.converge()

    assert run.status is ConvergeStatus.NO_CHANGE, (run.status, run.error)
    assert not [c for c in run.published.changes if c.path.startswith(GUIDE_TREE_PREFIX)]
    assert await _guide_doc(a) not in {c.path for c in run.published.changes}


# --- the upgrade path -------------------------------------------------------


def _older_build_publishes(remote_url: str, files: dict[str, str]) -> None:
    """A machine on a build without this rule pushes the guide, as it used to.

    Driven through plain git rather than a :class:`VaultMachine`, for the same
    reason ``harness.another_coffer_pushes`` is: a harness machine can only
    write what *this* build writes, and what is under test is what this build
    does with a tree another one left behind.
    """
    clone = pathlib.Path(remote_url).parent / "older-build"
    subprocess.run(
        ["git", "clone", "-b", BRANCH, remote_url, str(clone)], check=True, capture_output=True
    )
    for key, value in (("user.email", "old@localhost"), ("user.name", "Older Coffer")):
        subprocess.run(
            ["git", "-C", str(clone), "config", key, value], check=True, capture_output=True
        )
    assert (clone / MANIFEST_PATH).is_file(), "the remote must already be initialised"
    for rel, body in files.items():
        target = clone / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    for args in (["add", "-A"], ["commit", "-m", "older build"], ["push", "origin", BRANCH]):
        subprocess.run(["git", "-C", str(clone), *args], check=True, capture_output=True)


async def test_a_guide_an_older_build_published_is_ignored_and_left_alone(pair) -> None:
    """The mid-upgrade fleet, which is where this could still have gone wrong.

    Three things have to be true at once, and each is a different failure:

    * the arriving folder must not overwrite the master this machine rendered
      (an export-side rule alone cannot stop that);
    * the arriving row document must not be *applied* — ``ResourceApplier
      .remove`` would reach the skill kind's delete guard, raise
      ``ResourceProtected``, and be refused again on every tick because the
      round re-derives its diff each time;
    * and this machine must not publish the stale paths' **absence**, because a
      deletion is the one change every machine acts on, and the older build at
      the other end would take it as leave to unlink its own live master.

    The stale document sits at **this machine's own guide uid**, and that is
    the faithful reconstruction rather than a convenience: before the rule
    existed the guide converged like anything else, so the machine at the other
    end applied this one's document and registered the row under the identity
    it carried. One guide, one uid, two machines — which is exactly why the
    stale path is one this machine recognises as its own and withholds, rather
    than one it would sweep out of the tree as somebody's leftover.
    """
    a, _b = pair
    text_a = _guide_text("notes")
    a.write_knowledge("notes", "standup", "what we did\n")
    await _seed_guide(a, text_a)
    await settle(a)

    stale_uid = await a.uid("skill", GUIDE_SKILL_NAME)
    stale_guide_doc = f"resources/skill/{stale_uid}.yaml"
    stale_doc = json.dumps({"kind": "skill", "name": GUIDE_SKILL_NAME})
    _older_build_publishes(
        a.remote_url,
        {
            GUIDE_SKILL_MD: _guide_text("notes", "archive"),
            f"{GUIDE_TREE_PREFIX}.coffer.meta.json": stale_doc,
            stale_guide_doc: (
                f"config:\n  source:\n    type: builtin\n  value: {GUIDE_SKILL_NAME}\n"
                f"  version_hash: stale\nkind: skill\nname: {GUIDE_SKILL_NAME}\n"
                f"uid: {stale_uid}\n"
            ),
        },
    )

    run = await a.converge()

    assert run.status is not ConvergeStatus.AWAITING_CONFIRMATION, run.pending
    assert run.ok, (run.status, run.error)
    assert not run.failures, run.failures
    # The master and the row are exactly as this machine wrote them.
    assert _master(a) == text_a
    row = await a.resources.get_by_name("skill", GUIDE_SKILL_NAME)
    assert row.uid == stale_uid, "the same resource, which is what makes it stale"
    assert row.config["version_hash"] == _builtin_config(text_a)["version_hash"]

    # The stale copies are left where they are — inert, not deleted. Deleting
    # them would be a change the older build acts on; ignoring them is a change
    # nobody has to act on.
    remote = await a.remote_paths()
    assert GUIDE_SKILL_MD in remote
    assert stale_guide_doc in remote

    # ...and it stays that way, tick after tick, rather than being re-refused.
    again = await a.converge()
    assert again.status is ConvergeStatus.NO_CHANGE, (again.status, again.error)
    assert not again.failures
