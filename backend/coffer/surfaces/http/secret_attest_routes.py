"""``POST /api/v1/secrets/presence/attest`` — the daemon proves it is Coffer's.

The desktop shell trusts the port and token ``~/.coffer/daemon.json`` names, which
any process of the same user can rewrite. Before it signs a presence grant it
sends a random nonce here and checks the answer against its own derivation: only
a process that can read the master key can produce it. The port is part of the
signed text, so an answer relayed from the real daemon on another port is worth
nothing to a fake one.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from coffer.application.secret.presence import attest, derive_purpose_key
from coffer.domain.secret_errors import SecretMissing
from coffer.domain.secrets import DAEMON_ATTEST_KEY_CONTEXT
from coffer.surfaces.http import daemon_port
from coffer.surfaces.http.secret_composition import get_master_key_manager
from coffer.surfaces.http.secret_schemas import AttestIn, AttestOut

# Mounted on the secret boundary's router, which carries the prefix and the token.
router = APIRouter()


@router.post("/presence/attest", response_model=AttestOut)
async def presence_attest(
    body: AttestIn,
    manager: Any = Depends(get_master_key_manager),  # noqa: B008
) -> AttestOut:
    key = manager.current
    if not key:
        raise SecretMissing("master-key")
    attest_key = derive_purpose_key(key, DAEMON_ATTEST_KEY_CONTEXT)
    return AttestOut(signature=attest(attest_key, f"{body.nonce}\n{daemon_port.get_port()}"))
