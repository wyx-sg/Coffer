"""The machine dimension of a converged vault (spec vault-sync).

A vault that spans machines needs two things this file pins down. The
**registry** — one document per machine, at a path only that machine writes, so
that the thing every machine reads cannot conflict. And the boundary the
registry implies: what belongs to a machine rather than to the vault, and so
must not cross even though the machines share a remote.

Two things stay put. A resource's **reach** — whether it is live here, and for
which agents — is set on the machine it applies to, and each machine sets its
own. A **channel** is an inbound surface bound to one host: its webhook URL,
its tunnel, its port mean nothing anywhere else. Both are asserted here by
running two real vaults against one real bare repository, because both are
claims about what a converge round leaves behind, and a serializer test could
only assert what we believe the round does with it.

The channel rule's *inbound* half — that a diff deleting a channel document
must not delete a locally-registered channel — cannot be staged end to end,
because on this build no machine's export leaves a channel document in the tree
for a later merge to remove. It is asserted at the applier seam instead, in
``test_bundle_roundtrip.py``.

The machine ids here are injected, never derived: a test that read this host's
``IOPlatformUUID`` would be asserting something about the developer's laptop.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.application.sync.machines import CannotRetireSelfError
from coffer.domain.scope import Scope, is_active
from coffer.domain.sync.convergence import JoinKind
from coffer.domain.sync.machine import ID_LENGTH, derive_machine_id
from tests.integration.sync.harness import MACHINE_A, MACHINE_B, settle, two_machines

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


@pytest.mark.acceptance(spec="vault-sync", scenario="a channel does not travel")
async def test_a_channel_does_not_travel(pair) -> None:
    """A channel is a webhook URL, a tunnel and a port: one host's inbound
    surface. Travelling, it would at best be inert on the other machine and at
    worst come up and answer, so two machines would be taking turns in one
    conversation, each unaware of the other."""
    a, b = pair
    await a.register("channel", "seatalk-a", {"value": "port-8787"})
    await b.register("channel", "telegram-b", {"value": "port-9090"})
    await a.register("mcp_server", "travels", {"value": "t"})
    await settle(a, b)

    # A's channel did not arrive on B, and B's did not arrive on A.
    assert await b.resource_names("channel") == ["telegram-b"]
    assert await a.resource_names("channel") == ["seatalk-a"]
    # Each machine still holds the one it configured for itself — the round
    # neither imported a foreign channel nor disturbed the local one.
    assert await a.find("channel", "seatalk-a") is not None
    assert await b.find("channel", "telegram-b") is not None
    # A resource of a kind that *does* travel crossed in the same rounds, so
    # this is not a vault that simply failed to converge.
    assert "travels" in await b.resource_names("mcp_server")

    # Nothing channel-shaped was ever written to the remote either.
    remote = await a.remote_paths()
    assert not [p for p in remote if p.startswith("resources/channel/")]


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
