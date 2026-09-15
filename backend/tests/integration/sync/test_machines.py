"""The machine dimension of a converged vault (spec vault-sync).

A vault that spans machines needs two things this file pins down. The
**registry** — one document per machine, at a path only that machine writes, so
that the thing every machine reads cannot conflict. And the boundary the
registry implies: what belongs to a machine rather than to the vault, and so
must not cross even though the machines share a remote.

One thing stays put. A resource's **reach** — whether it is live here, and for
which agents — is set on the machine it applies to, and each machine sets its
own. It is asserted here by running two real vaults against one real bare
repository, because it is a claim about what a converge round leaves behind,
and a serializer test could only assert what we believe the round does with it.

A **channel** used to stay put with it, and no longer does. It travels like any
other resource and carries, inside its own config, the one machine whose daemon
runs its adapter — so what this file asserts about a channel is that the
document crosses and the BINDING crosses with it unaltered. What each machine's
runtime then does with that binding is asserted where the runtime is, in
``tests/integration/channel/test_runtime_binding.py``.

The machine ids here are injected, never derived: a test that read this host's
``IOPlatformUUID`` would be asserting something about the developer's laptop.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.application.channel.wanted import Gate
from coffer.application.sync.machines import CannotRetireSelfError
from coffer.domain.scope import Scope, is_active
from coffer.domain.sync.convergence import JoinKind
from coffer.domain.sync.machine import ID_LENGTH, derive_machine_id
from tests.integration.sync.harness import MACHINE_A, MACHINE_B, settle, two_machines


def _says(machine_id: str):
    """The Gate's machine-id provider, pinned to one machine."""

    async def _provider() -> str:
        return machine_id

    return _provider


pytestmark = pytest.mark.timeout(120)


@pytest.fixture
async def pair(tmp_path: pathlib.Path):
    a, b = await two_machines(tmp_path)
    yield a, b
    await a.close()
    await b.close()


@pytest.mark.acceptance(
    spec="vault-sync", scenario="the machine registry shows every machine and cannot conflict"
)
async def test_both_machines_appear_in_the_registry_with_no_conflict(pair) -> None:
    a, b = pair
    await a.register("agent", "claude-code", {"value": "cc"})
    await settle(a, b)

    on_a = {view.descriptor.machine_id: view for view in await a.machine_views()}
    on_b = {view.descriptor.machine_id: view for view in await b.machine_views()}

    assert set(on_a) == {MACHINE_A, MACHINE_B} == set(on_b)
    assert on_a[MACHINE_A].descriptor.name == "laptop"
    assert on_a[MACHINE_B].descriptor.name == "desktop"
    # Each machine marks itself, and only itself.
    assert on_a[MACHINE_A].is_self and not on_a[MACHINE_B].is_self
    assert on_b[MACHINE_B].is_self and not on_b[MACHINE_A].is_self
    # The last converged *day*, not an instant: an idle machine must not commit
    # a heartbeat every round.
    assert on_a[MACHINE_A].descriptor.last_converged_on is not None
    # Two machines with different keys can say so without comparing by hand.
    assert on_a[MACHINE_A].key_matches is True
    assert on_a[MACHINE_B].key_matches is False
    assert on_a[MACHINE_A].descriptor.agents == ("claude-code",)

    # The registry is one file per machine, which is why it cannot conflict:
    # two machines never stage a change to the same path.
    remote = await a.remote_paths()
    assert {p for p in remote if p.startswith("machines/")} == {
        f"machines/{MACHINE_A}.yaml",
        f"machines/{MACHINE_B}.yaml",
    }
    # And neither round reported one.
    assert (await a.converge()).conflicts == ()
    assert (await b.converge()).conflicts == ()


@pytest.mark.acceptance(
    spec="vault-sync", scenario="the machine registry shows every machine and cannot conflict"
)
async def test_a_machine_cannot_retire_itself_and_retiring_a_peer_touches_nothing_else(
    pair,
) -> None:
    a, b = pair
    await settle(a, b)

    with pytest.raises(CannotRetireSelfError):
        await a.registry.retire(a.bundle, MACHINE_A)

    # Retiring the *other* machine takes its descriptor and only that. Nothing
    # in the vault names a machine id any more — reach is machine-local, so no
    # scope can name one — so there is nothing left to leave dangling, and
    # nothing to rewrite behind the user's back. The old version rebuilt every
    # scope that named the id, and retiring the last machine a resource named
    # silently widened "only there" into "everywhere".
    await a.register("mcp_server", "desk-only", {"value": "d"})
    await a.set_scope("mcp_server", "desk-only", Scope(agents=["claude-code"]))

    await a.registry.retire(a.bundle, MACHINE_B)

    untouched = await a.find("mcp_server", "desk-only")
    assert untouched is not None
    assert untouched.scope == Scope(agents=["claude-code"])
    assert untouched.enabled is True
    assert [v.descriptor.machine_id for v in await a.machine_views()] == [MACHINE_A]


# --- reach ------------------------------------------------------------------


@pytest.mark.acceptance(spec="vault-sync", scenario="reach stays on the machine it was set on")
async def test_reach_stays_on_the_machine_it_was_set_on(pair) -> None:
    """The decision, end to end.

    Two machines hold the same server. One is told the server is off; the
    other is told it answers to a single agent. Neither instruction is a fact
    about the vault — it is a fact about the machine the user was sitting at —
    so converging must leave both standing. What does cross is the server
    itself: a configuration edit on either machine reaches the other, carrying
    no opinion about reach with it.
    """
    a, b = pair
    await a.register("mcp_server", "shared", {"value": "v1"})
    await settle(a, b)
    assert await b.find("mcp_server", "shared") is not None

    # Each machine answers the reach question for itself, differently.
    await a.set_enabled("mcp_server", "shared", False)
    await b.set_scope("mcp_server", "shared", Scope(agents=["codex"]))

    await settle(a, b)

    enabled_on_a, scope_on_a = await a.reach("mcp_server", "shared")
    enabled_on_b, scope_on_b = await b.reach("mcp_server", "shared")
    assert (enabled_on_a, scope_on_a) == (False, None), "A's 'off' was overwritten from B"
    assert (enabled_on_b, scope_on_b) == (True, Scope(agents=["codex"])), (
        "B's agent restriction was overwritten from A"
    )
    # Spelled out at the point of use: the restriction B set is still in force
    # there, and A — which never set one — still admits every agent.
    assert is_active(scope_on_b, "codex") is True
    assert is_active(scope_on_b, "claude-code") is False
    assert is_active(scope_on_a, "claude-code") is True

    # Neither machine published reach at all: the document in the shared tree
    # is identity, description and config, and that is the reason the two
    # answers above can coexist.
    doc = await a.remote_text("resources/mcp_server/shared.yaml")
    assert doc is not None
    assert "enabled" not in doc
    assert "scope" not in doc

    # And the resource itself still travels, in both directions — otherwise
    # this would be passing for the uninteresting reason that nothing crossed.
    await a.edit_config("mcp_server", "shared", {"value": "edited-on-a"})
    await settle(a, b)
    on_b = await b.find("mcp_server", "shared")
    assert on_b is not None and on_b.config["value"] == "edited-on-a"

    await b.edit_config("mcp_server", "shared", {"value": "edited-on-b"})
    await settle(a, b)
    on_a = await a.find("mcp_server", "shared")
    assert on_a is not None and on_a.config["value"] == "edited-on-b"

    # Two config edits crossed the remote in both directions, and neither
    # carried a reach with it.
    assert (await a.reach("mcp_server", "shared")) == (False, None)
    assert (await b.reach("mcp_server", "shared")) == (True, Scope(agents=["codex"]))


@pytest.mark.acceptance(spec="vault-sync", scenario="reach stays on the machine it was set on")
async def test_a_newly_arrived_resource_takes_this_machines_default_reach(pair) -> None:
    """The same rule, at the moment a resource is seen here for the first time.

    Nobody on this machine has said yet how far the arriving resource should
    reach, so the framework's own default is the right answer. Inheriting the
    other machine's would be the silent re-answering the document stopped
    carrying reach to prevent — and it is least visible here, where the user
    has nothing on this machine to compare it against.
    """
    a, b = pair
    await a.register("mcp_server", "fresh", {"value": "v"})
    await a.set_enabled("mcp_server", "fresh", False)
    await a.set_scope("mcp_server", "fresh", Scope(agents=[]))
    await settle(a, b)

    arrived = await b.find("mcp_server", "fresh")
    assert arrived is not None, "the resource itself must still cross"
    assert arrived.config["value"] == "v"
    # B's defaults, not A's answers: live, and restricted to nobody.
    assert arrived.enabled is True
    assert arrived.scope is None
    assert is_active(arrived.scope, "claude-code") is True
    # A kept what it set.
    assert (await a.reach("mcp_server", "fresh")) == (False, Scope(agents=[]))


# --- channels ---------------------------------------------------------------


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a channel travels and runs only on the machine it names"
)
async def test_a_channel_travels_carrying_the_machine_that_runs_it(pair) -> None:
    """The document crosses; the adapter does not.

    What makes that safe is one field. A channel names the machine whose daemon
    starts its adapter, so the copy that lands on the other machine is a
    complete, editable channel that machine simply does not run — and the test
    that matters at this layer is that the name SURVIVES the trip. A binding
    quietly rewritten or dropped in transit would leave the arriving channel
    looking like everyone's, which is the rival-consumer failure the whole
    design exists to prevent.
    """
    a, b = pair
    await a.register("channel", "seatalk-a", {"value": "port-8787", "runs_on": a.machine_id})
    await b.register("channel", "telegram-b", {"value": "port-9090", "runs_on": b.machine_id})
    await settle(a, b)

    # Both machines hold both channels now.
    assert await a.resource_names("channel") == ["seatalk-a", "telegram-b"]
    assert await b.resource_names("channel") == ["seatalk-a", "telegram-b"]

    # And each copy still names the machine that runs it — A's channel on B
    # says A, which is what stops B's runtime from starting an adapter for it.
    arrived = await b.find("channel", "seatalk-a")
    assert arrived.config["runs_on"] == a.machine_id
    assert (await a.find("channel", "telegram-b")).config["runs_on"] == b.machine_id

    # The reach of the arriving copy is this machine's own, as for every kind.
    assert await b.reach("channel", "seatalk-a") == (True, None)

    # The remote carries the documents, which it never used to.
    remote = await a.remote_paths()
    assert "resources/channel/seatalk-a.yaml" in remote
    assert "resources/channel/telegram-b.yaml" in remote

    # And the production gate, run against the rows that actually came off the
    # remote, answers the way the design needs it to. Asserting the FIELD
    # survived and asserting the GATE honours the field are two different
    # claims, and each has its own test elsewhere; this joins them on a row
    # that has been through YAML and a three-way merge, which is the only
    # place a binding could arrive intact but unreadable.
    on_b = await Gate(machine_id_provider=_says(b.machine_id)).wanted(b.resources)
    assert set(on_b) == {"telegram-b"}, "B must not start an adapter for A's channel"
    on_a = await Gate(machine_id_provider=_says(a.machine_id)).wanted(a.resources)
    assert set(on_a) == {"seatalk-a"}, "A must still run its own"


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="a synced channel carries a credential reference, never a secret",
)
async def test_a_travelling_channel_publishes_refs_and_not_secrets(pair) -> None:
    """A channel's config was always refs-only. Travelling is what makes that
    load-bearing rather than merely tidy: the document is now committed to a
    repository the user pushes somewhere."""
    a, b = pair
    a.set_credential("channel/tg/bot-token", "placeholder-not-a-real-bot-token")
    await a.register(
        "channel",
        "tg",
        {"value": "telegram", "credential_ref": "channel/tg/bot-token"},
    )
    await settle(a, b)

    document = await a.remote_text("resources/channel/tg.yaml")
    assert document is not None
    assert "channel/tg/bot-token" in document
    assert "placeholder-not-a-real-bot-token" not in document

    # And nowhere else in the tree either — a credential blob, if this remote
    # carries credentials at all, is Fernet ciphertext.
    for path in await a.remote_paths():
        text = await a.remote_text(path)
        assert text is None or "placeholder-not-a-real-bot-token" not in text


# --- identity ---------------------------------------------------------------


@pytest.mark.acceptance(spec="vault-sync", scenario="renaming a machine costs nothing")
async def test_renaming_a_machine_rewrites_nothing_in_the_vault(pair) -> None:
    a, b = pair
    await a.register("mcp_server", "shared", {"value": "d"})
    await settle(a, b)
    before = await b.find("mcp_server", "shared")
    assert before is not None

    await b.service().rename_self(b.registry, "the machine formerly known as desktop")
    await b.converge()
    await a.converge()

    # Not one resource was rewritten: the name lives in the descriptor, and
    # the descriptor is the only document in the vault that names a machine.
    after = await b.find("mcp_server", "shared")
    assert after is not None
    assert after.config == before.config
    assert after.updated_at == before.updated_at
    # And the new name reached the other machine, inside B's own descriptor.
    names = {v.descriptor.machine_id: v.descriptor.name for v in await a.machine_views()}
    assert names[MACHINE_B] == "the machine formerly known as desktop"


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a machine identity survives reinstalling Coffer"
)
async def test_a_reinstalled_machine_returns_under_the_same_id(tmp_path: pathlib.Path) -> None:
    """``~/.coffer`` is deleted and Coffer reinstalled on a host that exposes a
    stable identifier.

    The id is derived from the host, so it comes back the same — which is the
    whole reason it is derived rather than generated. Its descriptor is updated
    rather than duplicated, and the round recognises it as a machine that has
    been here before rather than as a stranger.
    """
    a, b = await two_machines(tmp_path)
    try:
        # The host identifier is what survives; the id is a function of it.
        raw_host_identifier = "1E4C0000-0000-0000-0000-DEADBEEF0000"
        assert derive_machine_id(raw_host_identifier) == derive_machine_id(raw_host_identifier)
        assert len(derive_machine_id(raw_host_identifier)) == ID_LENGTH
        assert raw_host_identifier not in derive_machine_id(raw_host_identifier)

        await a.register("mcp_server", "shared", {"value": "d"})
        await settle(a, b)
        assert (
            len([v for v in await a.machine_views() if v.descriptor.machine_id == MACHINE_B]) == 1
        )

        # The reinstall: local convergence state and the working tree go. The
        # machine id does not, because the host still answers with it.
        b.state.forget()
        b.forget_worktree()

        run = await b.converge()

        assert run.join is JoinKind.RETURNING
        views = await b.machine_views()
        # Updated, not duplicated.
        assert [v.descriptor.machine_id for v in views].count(MACHINE_B) == 1
        assert sorted(v.descriptor.machine_id for v in views) == sorted([MACHINE_A, MACHINE_B])
    finally:
        await a.close()
        await b.close()
