"""The registration secret probe, split out of ``resource_service``.

A resource citing a secret_ref is refused unless the ref has a value — or a
person's approval of its new value is pending, in which case the value arrives
with the approval (spec mcp-gateway "Manage MCP servers as resources").
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Protocol

from coffer.application import resource_kind_ops
from coffer.domain.resource import Kind
from coffer.domain.secret_errors import SecretMissing


class _SecretGetter(Protocol):
    def get(self, ref: str) -> Any: ...


async def probe_secrets(
    secrets: _SecretGetter,
    awaiting: Callable[[str], bool] | None,
    kind_def: Kind,
    config: dict[str, Any],
) -> None:
    """Raise SecretMissing for the first cited ref with neither a value nor a pending approval.

    Called BEFORE persisting a Resource so a missing secret never leaves a
    partial resource file behind. The store's ``get`` is a blocking file read,
    so it (and the approval lookup) runs in a worker thread rather than on the
    loop.
    """
    for _key, ref in resource_kind_ops.secret_refs(kind_def, config).items():
        if await asyncio.to_thread(secrets.get, ref) is not None:
            continue
        if awaiting is not None and await asyncio.to_thread(awaiting, ref):
            continue
        raise SecretMissing(ref)
