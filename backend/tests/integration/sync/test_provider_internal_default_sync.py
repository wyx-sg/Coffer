"""A synced second internal-engine default is dropped, not fatal.

Spec provider-switching "Keep at most one internal-engine default", on the sync
path (spec vault-sync). Two machines can each flag a different connection
between rounds; the tree then carries two flagged documents, and the partial
unique index ``ux_provider_single_internal_default`` refuses the second. That
used to surface as a raw ``IntegrityError`` out of the apply step — after the
snapshot, before the pointer — so the round aborted and every later round
aborted the same way (and a NEW connection was misreported as already existing
and held for retry).

Driven through the production round over two real vaults and a real remote, so
the round, the pointer and the held set are the real ones.
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest

from coffer.domain.sync.convergence import ConvergeStatus
from tests.integration.sync.harness import VaultMachine, settle, two_machines

pytestmark = pytest.mark.timeout(120)


def _ollama(host: str, *, flagged: bool = False) -> dict[str, Any]:
    """A keyless connection, so no credential has to cross machines."""
    return {"protocol": "ollama", "base_url": f"http://{host}:11434", "internal_default": flagged}


@pytest.fixture
async def pair(tmp_path: pathlib.Path):
    a, b = await two_machines(tmp_path)
    yield a, b
    await a.close()
    await b.close()


async def _flag(machine: VaultMachine, name: str) -> bool:
    row = await machine.find("provider", name)
    assert row is not None, f"provider/{name} is not registered on {machine.name}"
    return row.config["internal_default"] is True


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a synced second internal default is dropped, not fatal",
)
async def test_an_incoming_flag_on_an_existing_connection_is_dropped(pair) -> None:  # type: ignore[no-untyped-def]
    a, b = pair
    await a.register("provider", "theirs", _ollama("theirs"))
    await settle(a, b)
    path = await a.doc_path("provider", "theirs")

    # Between rounds, each machine flags a different connection: B its own new
    # one, A the shared one (A has not seen B's yet), with another edit beside it.
    await b.register("provider", "mine", _ollama("mine", flagged=True))
    await a.edit_config("provider", "theirs", _ollama("theirs-v2", flagged=True))
    await a.converge()

    run = await b.converge()

    # The round completes and the pointer moves to what it applied.
    assert run.status is ConvergeStatus.OK, run.error
    assert await b.state.pointer() == run.commit
    # The flag already held here keeps it...
    assert await _flag(b, "mine") is True
    # ...and the incoming document is applied in everything but the flag.
    theirs = await b.find("provider", "theirs")
    assert theirs is not None
    assert theirs.config["base_url"] == "http://theirs-v2:11434"
    assert theirs.config["internal_default"] is False
    # Reported, naming the path and the connection that kept the flag...
    assert [p for p, _reason in run.failures] == [path]
    assert "'mine'" in run.failures[0][1]
    # ...but not held: a retry would meet the same rows every round.
    retry, not_applicable = await b.state.held_paths()
    assert path not in retry and path not in not_applicable

    again = await b.converge()
    assert again.status in (ConvergeStatus.OK, ConvergeStatus.NO_CHANGE), again.error
    assert again.failures == ()
    assert await _flag(b, "mine") is True


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a synced second internal default is dropped, not fatal",
)
async def test_an_incoming_flag_on_a_new_connection_is_dropped(pair) -> None:  # type: ignore[no-untyped-def]
    a, b = pair
    await settle(a, b)

    await b.register("provider", "mine", _ollama("mine", flagged=True))
    await a.register("provider", "theirs", _ollama("theirs", flagged=True))
    await a.converge()
    path = await a.doc_path("provider", "theirs")

    run = await b.converge()

    assert run.status is ConvergeStatus.OK, run.error
    assert await b.state.pointer() == run.commit
    # Registered here at the identity it carries — not refused as a duplicate.
    theirs = await b.find("provider", "theirs")
    assert theirs is not None and theirs.uid == await a.uid("provider", "theirs")
    assert theirs.config["base_url"] == "http://theirs:11434"
    assert theirs.config["internal_default"] is False
    assert await _flag(b, "mine") is True
    assert [p for p, _reason in run.failures] == [path]
    assert "'mine'" in run.failures[0][1]
    retry, _not_applicable = await b.state.held_paths()
    assert path not in retry


async def test_a_flag_moved_on_another_machine_lands_whatever_the_apply_order(pair) -> None:  # type: ignore[no-untyped-def]
    """A move is not a conflict: the tree clears the old holder in the same round.

    The uids are chosen so the newly flagged document applies BEFORE the old
    holder's release — the order in which a normaliser that looked only at
    this machine's rows would drop the move, leaving no default here at all.
    """
    a, b = pair
    await a.resources.register(
        "provider", "old", _ollama("old", flagged=True), "test", uid="f" * 32
    )
    await settle(a, b)
    assert await _flag(b, "old") is True

    # What the dedicated route does on A: clear the holder, then mark the target.
    await a.edit_config("provider", "old", _ollama("old"))
    await a.resources.register(
        "provider", "new", _ollama("new", flagged=True), "test", uid="0" * 32
    )
    await a.converge()

    run = await b.converge()

    assert run.status is ConvergeStatus.OK, run.error
    assert run.failures == ()
    assert await _flag(b, "new") is True
    assert await _flag(b, "old") is False
