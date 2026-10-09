"""Each kind files its resources in the class its nature asks for (ADR
storage-is-five-classes-by-nature): an agent names a directory on this disk
(``local/``), Coffer's own skill is rebuilt
(``derived/``), everything a person chose is in the vault."""

from __future__ import annotations

import pytest

from coffer.application.agent.kind import make_agent_kind
from coffer.application.skill.kind import make_skill_kind
from coffer.domain.skill.builtin import BUILTIN_SOURCE_TYPE
from coffer.domain.vault.layout import StorageClass


async def _noop(_resource: object) -> None:
    return None


def test_an_agent_is_local() -> None:
    kind = make_agent_kind()
    assert kind.storage is StorageClass.LOCAL and kind.storage_row is None


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a locally generated skill is neither published nor overwritten"
)
def test_coffers_own_skill_is_derived_and_every_other_skill_is_in_the_vault() -> None:
    kind = make_skill_kind(_noop)
    assert kind.storage_row is not None
    assert kind.storage_row({"source": {"type": BUILTIN_SOURCE_TYPE}}) is StorageClass.DERIVED
    assert kind.storage_row({"source": {"type": "git"}}) is StorageClass.VAULT
