"""The machine dimension of a converged vault (spec vault-sync).

A vault that spans machines needs two things this file pins down. The
**registry** — one document per machine, at a path only that machine writes, so
that the thing every machine reads cannot conflict. And the **machine axis of
scope** — keyed by the derived id and never by the display name, which is what
makes renaming a machine free and makes a resource dormant somewhere without
being absent there.

The machine ids here are injected, never derived: a test that read this host's
``IOPlatformUUID`` would be asserting something about the developer's laptop.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.application.scope_evaluator import ScopeEvaluator
from coffer.application.sync.machines import CannotRetireSelfError
from coffer.domain.scope import Scope
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
async def test_a_machine_cannot_retire_itself(pair) -> None:
    a, b = pair
    await settle(a, b)

    with pytest.raises(CannotRetireSelfError):
        await a.registry.retire(a.bundle, MACHINE_A, actor="user")

    # Retiring the *other* machine takes its descriptor and every scope naming
    # it, in one change — a descriptor removed while scopes still name the id
    # would leave resources dormant on a machine nobody can see.
    await a.register("mcp_server", "desk-only", {"value": "d"})
    await a.set_scope("mcp_server", "desk-only", Scope(machines=[MACHINE_B]))

    touched = await a.registry.retire(a.bundle, MACHINE_B, actor="user")

    assert touched == 1
    scoped = await a.find("mcp_server", "desk-only")
    assert scoped is not None and scoped.scope == Scope(agents=None, machines=None)
    assert [v.descriptor.machine_id for v in await a.machine_views()] == [MACHINE_A]


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a resource is dormant on a machine outside its scope"
)
async def test_a_machine_scoped_server_converges_everywhere_and_activates_in_one_place(
    pair,
) -> None:
    """Scope says *where a resource runs*, not *where it exists*.

    The row travels and is visible on both machines — that is what makes the
    scope editable from either of them — while the gateway exposes its tools
    only where the machine axis matches.
    """
    a, b = pair
    await a.register("mcp_server", "desk-only", {"value": "d"})
    await a.set_scope("mcp_server", "desk-only", Scope(machines=[MACHINE_B]))
    await a.register("mcp_server", "everywhere", {"value": "e"})
    await settle(a, b)

    # Registered and visible on both.
    assert "desk-only" in await a.resource_names("mcp_server")
    assert "desk-only" in await b.resource_names("mcp_server")
    on_b = await b.find("mcp_server", "desk-only")
    assert on_b is not None and on_b.scope == Scope(agents=None, machines=[MACHINE_B])

    # Active on B, dormant on A, and A can say which axis excluded it.
    here = ScopeEvaluator(machine_id=MACHINE_A)
    there = ScopeEvaluator(machine_id=MACHINE_B)
    assert here.is_active(on_b.scope, "claude-code") is False
    assert here.excluded_by(on_b.scope, "claude-code") == "machine"
    assert there.is_active(on_b.scope, "claude-code") is True
    # The unscoped one is active in both places, so this is not a blanket "off".
    unscoped = await a.find("mcp_server", "everywhere")
    assert unscoped is not None
    assert here.is_active(unscoped.scope, "claude-code") is True


@pytest.mark.acceptance(spec="vault-sync", scenario="renaming a machine costs nothing")
async def test_renaming_a_machine_leaves_every_scope_that_names_it_matching(pair) -> None:
    a, b = pair
    await a.register("mcp_server", "desk-only", {"value": "d"})
    await a.set_scope("mcp_server", "desk-only", Scope(machines=[MACHINE_B]))
    await settle(a, b)
    before = await b.find("mcp_server", "desk-only")
    assert before is not None

    await b.service().rename_self(b.registry, "the machine formerly known as desktop")
    await b.converge()
    await a.converge()

    # Not one resource was rewritten: scope references the derived id, and the
    # name lives in the descriptor.
    after = await b.find("mcp_server", "desk-only")
    assert after is not None
    assert after.scope == before.scope == Scope(agents=None, machines=[MACHINE_B])
    assert ScopeEvaluator(machine_id=MACHINE_B).is_active(after.scope, "claude-code") is True
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
    rather than duplicated, resources scoped to it are active again, and the
    round recognises it as a machine that has been here before.
    """
    a, b = await two_machines(tmp_path)
    try:
        # The host identifier is what survives; the id is a function of it.
        raw_host_identifier = "1E4C0000-0000-0000-0000-DEADBEEF0000"
        assert derive_machine_id(raw_host_identifier) == derive_machine_id(raw_host_identifier)
        assert len(derive_machine_id(raw_host_identifier)) == ID_LENGTH
        assert raw_host_identifier not in derive_machine_id(raw_host_identifier)

        await a.register("mcp_server", "desk-only", {"value": "d"})
        await a.set_scope("mcp_server", "desk-only", Scope(machines=[MACHINE_B]))
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
        # And the resource scoped to it is active here again.
        scoped = await b.find("mcp_server", "desk-only")
        assert scoped is not None
        assert ScopeEvaluator(machine_id=b.machine_id).is_active(scoped.scope, "claude-code")
    finally:
        await a.close()
        await b.close()
