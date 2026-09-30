"""Two machines that each flag a different internal default (spec
provider-switching "Keep at most one internal default connection"): the merged
tree would hold two, the vault's resource rule refuses it, and the round stops
on the file rather than checking out a second flag or dropping one silently."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from coffer.application.sync.round_join import join
from coffer.application.vault.resource_rules import resource_rule
from coffer.application.vault.validation import VaultValidator
from coffer.domain.resource import Kind
from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.rounds import RoundStatus

from .machines import Machine, bare_remote, resource


class _Connection(BaseModel):
    model_config = ConfigDict(extra="allow")
    internal_default: bool = False


def _validator() -> VaultValidator:
    kinds = {
        "provider": Kind(
            name="provider",
            display_name="Provider",
            config_schema=_Connection,
            exclusive_flags=("internal_default",),
        )
    }
    validator = VaultValidator()
    validator.register("resources/", resource_rule(kinds, lambda: {}))
    return validator


def _connection(name: str, uid: str, *, flagged: bool) -> bytes:
    return resource("provider", name, uid, {"internal_default": flagged})


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="two machines that each set a different internal default stop the round",
)
def test_two_internal_defaults_in_one_merged_tree_stop_the_round(tmp_path: Path) -> None:
    remote = SyncRemote(url=str(bare_remote(tmp_path)))
    mac = Machine(tmp_path / "mac", "MacBook Pro", remote, validate=_validator())
    mini = Machine(tmp_path / "mini", "Mac mini", remote, validate=_validator())
    join(mac.engine, remote, None)
    join(mini.engine, remote, None)

    mac.put("resources/provider/x.json", _connection("x", "a" * 32, flagged=True))
    mini.put("resources/provider/y.json", _connection("y", "b" * 32, flagged=True))
    assert mac.round().status is RoundStatus.PUSHED
    head = mini.repo.head()

    got = mini.round()
    assert got.status is RoundStatus.STOPPED
    stop = mini.state.stop()
    assert stop is not None
    assert {c.path for c in stop.conflicts} & {
        "resources/provider/x.json",
        "resources/provider/y.json",
    }
    # Nothing was checked out: this machine still holds only its own flag.
    assert mini.repo.head() == head
    assert mini.disk("resources/provider/x.json") is None
