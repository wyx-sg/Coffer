"""Which machine owns the curation pass, as a surface has to report it.

`GlobalInternalEngineConfig.curate_runs_on` answers the timer and may only say
yes or no. This covers `curation_owner`, which answers the **user** — and the
distinction it draws that a boolean cannot is the point: "another machine is
curating" and "nobody is curating, because the machine named no longer exists"
are both "not here" to the timer, and only one of them is a fault.

Covers `openspec/specs/knowledge/spec.md` and `openspec/specs/vault-sync/spec.md`
"Report and change the rewriter's owner".
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.domain.internal_engine_config import (
    CurationOwner,
    GlobalInternalEngineConfig,
)

SELF = "b7a5160dc1ef128f"
OTHER = "0f1e2d3c4b5a6978"
GONE = "deadbeefdeadbeef"


def _config(owner: str | None, *, enabled: bool = True) -> GlobalInternalEngineConfig:
    return GlobalInternalEngineConfig(
        model="a-model",
        updated_at=datetime.now(tz=UTC),
        auto_curate_enabled=enabled,
        curate_owner_machine_id=owner,
    )


def test_no_owner_named_is_unowned_not_a_fault() -> None:
    """A vault that never named an owner is a vault with one machine."""
    assert _config(None).curation_owner(SELF, [SELF]) is CurationOwner.UNOWNED


def test_the_owner_being_this_machine_reads_as_self() -> None:
    assert _config(SELF).curation_owner(SELF, [SELF, OTHER]) is CurationOwner.SELF


def test_an_owner_the_registry_holds_reads_as_another_machine() -> None:
    """Not a fault: the pass is running, just not here."""
    assert _config(OTHER).curation_owner(SELF, [SELF, OTHER]) is CurationOwner.OTHER


def test_an_owner_no_registry_entry_claims_is_the_fault() -> None:
    """The state this whole predicate exists for.

    `curate_runs_on` says False here, exactly as it says False for an owner
    that is another live machine — and the difference between those two is a
    vault that is fine and a vault whose curation stopped everywhere with
    nothing saying why.
    """
    config = _config(GONE)

    assert config.curation_owner(SELF, [SELF, OTHER]) is CurationOwner.UNKNOWN
    assert config.curate_runs_on(SELF) is False


def test_an_empty_registry_never_yields_the_fault() -> None:
    """A vault that has never converged has no registry at all.

    Reading that as "the owner does not exist" would report a fault on every
    single-machine install that had named its own machine — which is every
    install seeded by the migration. Same rule, same reason, as the frontend's
    `bindingState`.
    """
    assert _config(OTHER).curation_owner(SELF, []) is CurationOwner.OTHER
    assert _config(SELF).curation_owner(SELF, []) is CurationOwner.SELF


def test_a_machine_that_does_not_know_its_own_id_still_resolves() -> None:
    """Before the registry is read this machine's id can be None. An owner is
    then never `SELF`, which is the conservative answer — it reports as
    somewhere else rather than claiming a pass this machine may not run."""
    assert _config(SELF).curation_owner(None, [SELF]) is CurationOwner.OTHER


@pytest.mark.parametrize("owner", [None, SELF, OTHER, GONE])
def test_the_switch_being_off_does_not_hide_the_owner(owner: str | None) -> None:
    """Whether the pass is on and where it would run are two facts.

    Folding them would hide the owner precisely when someone is looking at the
    switch, about to turn it on.
    """
    off = _config(owner, enabled=False)
    on = _config(owner, enabled=True)

    assert off.curation_owner(SELF, [SELF, OTHER]) is on.curation_owner(SELF, [SELF, OTHER])
    assert off.curate_runs_on(SELF) is False
