"""A stand-in for the secret boundary's approvals list, for CLI test daemons.

After a register or edit the CLI asks ``GET /secrets/approvals`` which
approvals the resource waits on. A test daemon that wires only the resource
routes mounts this router so that question answers "none".
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/secrets")


@router.get("/approvals")
def list_no_approvals() -> dict[str, list[object]]:
    return {"approvals": []}
