"""A moved internal default is released only when the move lands here.

Spec provider-switching "Keep at most one internal-engine default", on the sync
path. When the tree moves the flag — the newly flagged connection's document
beside one clearing it on this machine's holder — the holder is released just
before the target is written, after the target's gate. A target that the gate
refuses, or whose own write fails, therefore leaves the holder with the flag:
this machine keeps an internal default rather than being left with none.

Driven through the production :class:`ResourceApplier` and
:class:`ProviderInternalDefaultNormaliser` over a real vault, one path at a
time, so the holder's own document never gets its turn and cannot mask what
the target's apply did.
"""

from __future__ import annotations

import pathlib
from collections.abc import AsyncIterator, Mapping
from typing import Any

import pytest
import yaml

from coffer.application.provider.internal_default_guard import ProviderInternalDefaultNormaliser
from coffer.application.sync.appliers_resource import ResourceApplier
from coffer.domain.error_base import CofferError
from tests.integration.sync.harness import VaultMachine, two_machines

pytestmark = pytest.mark.timeout(60)

_OLD = "f" * 32
_NEW = "0" * 32


def _ollama(host: str, *, flagged: bool) -> dict[str, Any]:
    return {"protocol": "ollama", "base_url": f"http://{host}:11434", "internal_default": flagged}


class _RefusedError(CofferError):
    code = "TEST_REFUSED"


class _RefusingGate:
    kind = "provider"

    async def validate(self, config: Mapping[str, object]) -> None:
        if config.get("base_url") == "http://new:11434":
            raise _RefusedError("this machine cannot take the new connection")


@pytest.fixture
async def machine(tmp_path: pathlib.Path) -> AsyncIterator[VaultMachine]:
    a, b = await two_machines(tmp_path)
    await a.resources.register("provider", "old", _ollama("old", flagged=True), "test", uid=_OLD)
    yield a
    await a.close()
    await b.close()


def _tree(root: pathlib.Path) -> pathlib.Path:
    """A tree that moves the flag from ``old`` to a new connection."""
    for uid, name, config in (
        (_NEW, "new", _ollama("new", flagged=True)),
        (_OLD, "old", _ollama("old", flagged=False)),
    ):
        path = root / "resources" / "provider" / f"{uid}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = {"uid": uid, "kind": "provider", "name": name, "config": config}
        path.write_text(yaml.safe_dump(doc))
    return root


def _applier(machine: VaultMachine, tree: pathlib.Path, **kw: Any) -> ResourceApplier:
    return ResourceApplier(
        machine.resources,
        worktree=tree,
        normalisers=[ProviderInternalDefaultNormaliser(machine.resources)],
        home=str(machine.home),
        **kw,
    )


async def _flag(machine: VaultMachine, name: str) -> bool | None:
    row = await machine.find("provider", name)
    return None if row is None else row.config["internal_default"] is True


async def test_a_move_releases_the_holder_when_the_target_lands(
    machine: VaultMachine, tmp_path: pathlib.Path
) -> None:
    applier = _applier(machine, _tree(tmp_path / "tree"))

    note = await applier.upsert(f"resources/provider/{_NEW}.yaml")

    assert note is None
    assert await _flag(machine, "new") is True
    assert await _flag(machine, "old") is False


async def test_a_move_the_gate_refuses_leaves_the_holder_its_flag(
    machine: VaultMachine, tmp_path: pathlib.Path
) -> None:
    applier = _applier(machine, _tree(tmp_path / "tree"), gates=[_RefusingGate()])

    with pytest.raises(_RefusedError):
        await applier.upsert(f"resources/provider/{_NEW}.yaml")

    assert await _flag(machine, "new") is None
    assert await _flag(machine, "old") is True


async def test_a_move_whose_target_write_fails_leaves_the_holder_its_flag(
    machine: VaultMachine, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    applier = _applier(machine, _tree(tmp_path / "tree"))

    async def failing_register(*_a: object, **_k: object) -> None:
        raise _RefusedError("the connection could not be written")

    monkeypatch.setattr(machine.resources, "register", failing_register)

    with pytest.raises(_RefusedError):
        await applier.upsert(f"resources/provider/{_NEW}.yaml")

    assert await _flag(machine, "new") is None
    assert await _flag(machine, "old") is True
