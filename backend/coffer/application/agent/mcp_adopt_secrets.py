"""The secrets half of adopting an MCP entry (spec agent-registry "Route
secret-like environment values to the secret store on adoption").

Adopting only ever CREATES refs. Writing over one that exists would change what
every resource citing it receives, a rollback would delete it under them, and a
standalone ``secret/<name>`` is a person's to name, not an adopt's.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Mapping
from typing import Protocol

from coffer.domain.agent.mcp_entries import McpEntry
from coffer.domain.workspace_errors import AdoptSecretRefExists


class SecretStorePort(Protocol):
    """The slice of the secret store adoption uses (values flow IN, never out)."""

    def set(self, ref: str, value: str) -> None: ...

    def delete(self, ref: str) -> None: ...

    def exists(self, ref: str) -> bool: ...


async def write_new_refs(store: SecretStorePort, refs: Mapping[str, str], entry: McpEntry) -> None:
    """Store each flagged value of ``entry`` under its ``refs`` entry.

    Refuses (``AdoptSecretRefExists``) a ref that already holds a value, before
    anything is written. The writes run in one worker thread: off the loop, and
    once started they finish even if the awaiting task is cancelled, so a
    partial write is always rolled back.
    """

    def _taken() -> list[str]:
        return [r for r in set(refs.values()) if store.exists(r)]

    taken = await asyncio.to_thread(_taken)
    if taken:
        raise AdoptSecretRefExists(taken)

    def _write() -> None:
        written: list[str] = []
        try:
            for key, ref in refs.items():
                value = entry.env[key] if key in entry.env else entry.headers[key]
                store.set(ref, value)
                written.append(ref)
        except Exception:
            for ref in written:
                with contextlib.suppress(Exception):
                    store.delete(ref)
            raise

    await asyncio.to_thread(_write)


async def drop_new_refs(store: SecretStorePort, refs: Mapping[str, str]) -> None:
    """Remove the refs this adoption created (all of them were new)."""

    def _delete_all() -> None:
        for ref in refs.values():
            with contextlib.suppress(Exception):
                store.delete(ref)

    await asyncio.to_thread(_delete_all)
