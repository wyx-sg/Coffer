"""A resource's title travels with its document (spec vault-sync "Converge
resource definitions as serialized documents").

The title is display text, not reach: it is part of the resource, so it
converges exactly as its description does. The one difference is on the wire —
the document carries a ``title`` key only when there is a title, so a document
without one means "no title" on the machine that applies it.
"""

from __future__ import annotations

import dataclasses
import pathlib

import pytest
import yaml

from tests.integration.sync.harness import VaultMachine, settle, two_machines

pytestmark = pytest.mark.timeout(120)


async def _title(machine: VaultMachine, kind: str, name: str) -> str | None:
    resource = await machine.find(kind, name)
    assert resource is not None, f"{kind}/{name} is not on {machine.name}"
    return resource.title


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a title set on one machine converges to the other"
)
async def test_a_title_set_on_one_machine_converges_to_the_other(tmp_path: pathlib.Path):
    a, b = await two_machines(tmp_path)
    await a.register("mcp_server", "wiki")
    await settle(a, b)
    uid = await a.uid("mcp_server", "wiki")
    assert await b.uid("mcp_server", "wiki") == uid
    assert await _title(a, "mcp_server", "wiki") is None
    assert await _title(b, "mcp_server", "wiki") is None

    await a.resources.set_title(uid, "Team wiki", "test")
    await settle(a, b)

    # The same resource, under the same name, now shows the same title.
    assert await _title(b, "mcp_server", "wiki") == "Team wiki"
    assert await b.uid("mcp_server", "wiki") == uid
    doc = yaml.safe_load(await a.remote_text(await a.doc_path("mcp_server", "wiki")) or "")
    assert doc["title"] == "Team wiki"

    # Cleared on the OTHER machine, and converged: empty on both.
    await b.resources.set_title(uid, "", "test")
    await settle(a, b)
    assert await _title(a, "mcp_server", "wiki") is None
    assert await _title(b, "mcp_server", "wiki") is None
    doc = yaml.safe_load(await a.remote_text(await a.doc_path("mcp_server", "wiki")) or "")
    assert "title" not in doc


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a document without a title leaves the title empty"
)
async def test_a_document_without_a_title_registers_and_updates_with_an_empty_title(
    tmp_path: pathlib.Path,
):
    a, b = await two_machines(tmp_path)
    await a.register("mcp_server", "wiki", {"value": "one"})
    await settle(a, b)
    uid = await a.uid("mcp_server", "wiki")
    # Registered on b from a document carrying no ``title`` key.
    doc = yaml.safe_load(await a.remote_text(await a.doc_path("mcp_server", "wiki")) or "")
    assert "title" not in doc
    assert await _title(b, "mcp_server", "wiki") is None

    # Both machines hold a title; then a clears it and edits the resource, and
    # publishes a document that carries no title. Applying it updates every
    # field it carries and leaves the title empty.
    await b.resources.set_title(uid, "Team wiki", "test")
    await settle(a, b)
    assert await _title(a, "mcp_server", "wiki") == "Team wiki"
    await a.resources.set_title(uid, None, "test")
    await a.resources.update_config(
        uid, {"value": "two"}, "test", description="now described", allow_lifecycle_kind=True
    )
    await settle(a, b)

    arrived = await b.find("mcp_server", "wiki")
    assert arrived is not None
    assert arrived.config["value"] == "two"
    assert arrived.description == "now described"
    assert arrived.title is None
    assert await _title(a, "mcp_server", "wiki") is None


async def _converge(machine: VaultMachine) -> list[object]:
    """One round on ``machine`` (joining first if it has not), and its failures."""
    if await machine.state.pointer() is None:
        run = await machine.adopt()
    else:
        run = await machine.converge()
    return list(run.failures)


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a title on a kind without one is ignored on apply"
)
async def test_a_title_on_a_kind_without_one_is_ignored_on_apply(tmp_path: pathlib.Path):
    """Machine ``a`` stands for an older build, whose ``mcp_server`` still carried
    a title and wrote it into the document; machine ``b`` runs this build, where
    the kind carries none (``Kind.titled=False``, as production declares it).
    ``b`` registers and then updates the server from those documents, with no
    title and no failure."""
    a, b = await two_machines(tmp_path)
    kinds = b.resources._kinds
    kinds["mcp_server"] = dataclasses.replace(kinds["mcp_server"], titled=False)

    await a.register("mcp_server", "wiki", {"value": "one"})
    uid = await a.uid("mcp_server", "wiki")
    await a.resources.set_title(uid, "Team wiki", "test")
    assert await _converge(a) == []
    doc = yaml.safe_load(await a.remote_text(await a.doc_path("mcp_server", "wiki")) or "")
    assert doc["title"] == "Team wiki", "precondition: the older build wrote a title"

    # Registered from the document, with no title and no failure.
    assert await _converge(b) == []
    arrived = await b.find("mcp_server", "wiki")
    assert arrived is not None
    assert (arrived.uid, arrived.config["value"], arrived.title) == (uid, "one", None)

    # Updated from the next document — which still carries the title — the same way.
    await a.edit_config("mcp_server", "wiki", {"value": "two"})
    assert await _converge(a) == []
    assert await _converge(b) == []
    arrived = await b.find("mcp_server", "wiki")
    assert arrived is not None
    assert (arrived.config["value"], arrived.title) == ("two", None)
