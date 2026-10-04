"""The registration secret probe, split out of ``resource_service``.

A resource citing a secret_ref is refused unless the ref has a value (spec
mcp-gateway "Manage MCP servers as resources").
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

from coffer.application import resource_kind_ops
from coffer.domain.resource import Kind
from coffer.domain.secret_errors import SecretMissing


class _SecretGetter(Protocol):
    def get(self, ref: str) -> Any: ...


async def probe_secrets(
    secrets: _SecretGetter,
    kind_def: Kind,
    config: dict[str, Any],
) -> None:
    """Raise SecretMissing for the first cited ref with no value.

    Called BEFORE persisting a Resource so a missing secret never leaves a
    partial resource file behind. The store's ``get`` is a blocking file read,
    so it runs in a worker thread rather than on the
    loop.
    """
    for _key, ref in resource_kind_ops.secret_refs(kind_def, config).items():
        if await asyncio.to_thread(secrets.get, ref) is not None:
            continue
        raise SecretMissing(ref)
