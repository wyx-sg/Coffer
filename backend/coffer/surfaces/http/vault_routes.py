"""``/api/v1/vault`` — the hand edits validation refused (spec vault-storage
"List the hand edits the vault kept out") and the hand-off that asks the
person's agent to bring an earlier version of a vault file back ("Hand
restoring an earlier version of a vault file to an agent").

The vault's history is git's: Coffer lists, diffs and restores no version. The
hand-off route writes nothing and records no audit event; the commit the agent
makes is validated like any other change to the vault.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from coffer.domain.vault.handoffs import history_spec, log_command, restore_handoff
from coffer.infrastructure.vault.home import vault_root
from coffer.infrastructure.vault.instance import vault_writer
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.handoff_schemas import HandoffOut
from coffer.surfaces.http.vault_schemas import (
    VaultHistoryHandoffIn,
    VaultHistoryHandoffOut,
    VaultProblemsOut,
    problem_out,
)

router = APIRouter(prefix="/api/v1/vault", tags=["vault"], dependencies=[Depends(require_token)])


@router.post("/history/handoff", response_model=VaultHistoryHandoffOut)
async def vault_history_handoff(body: VaultHistoryHandoffIn) -> VaultHistoryHandoffOut:
    """The prompt, the ``git log`` command and the locations for restoring a
    vault file or folder, optionally to a time; a path under ``secret/`` or
    outside the vault is refused."""
    spec = history_spec(body.path)
    vault = str(vault_root().expanduser())
    return VaultHistoryHandoffOut(
        path=spec,
        absolute_path=f"{vault}/{spec}",
        vault_path=vault,
        log_command=log_command(vault, spec),
        handoff=HandoffOut(prompt=restore_handoff(vault, spec, body.at)),
    )


@router.get("/problems", response_model=VaultProblemsOut)
async def vault_problems() -> VaultProblemsOut:
    """Hand edits validation refused: still on disk, uncommitted, with ``HEAD``
    in effect until each is fixed."""
    found = vault_writer().problems()
    return VaultProblemsOut(
        problems=[problem_out(f) for _path, items in sorted(found.items()) for f in items]
    )


__all__ = ["router"]
