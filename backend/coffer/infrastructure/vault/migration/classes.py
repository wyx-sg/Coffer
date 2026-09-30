"""Which class directory each migrated resource is filed in.

The kinds declare this themselves (``Kind.storage``, ``Kind.storage_row``),
but building the kinds needs the services the daemon wires, which a one-time
step run with the daemon stopped does not have. So the upgrade states the
same rule for the kinds of the previous build, and a contract test holds it
to the kinds' own declarations (``tests/integration/migration``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from coffer.domain.skill.builtin import is_builtin
from coffer.domain.vault.layout import StorageClass

#: Kinds whose every resource is filed outside the vault.
_BY_KIND = {"agent": StorageClass.LOCAL, "memory": StorageClass.DERIVED}


def storage_of(kind: str, config: Mapping[str, Any]) -> StorageClass:
    """Agents are this machine's; memory partitions and Coffer's own skill
    are derived; every other resource is the person's, in the vault."""
    if kind == "skill" and is_builtin(config):
        return StorageClass.DERIVED
    return _BY_KIND.get(kind, StorageClass.VAULT)


__all__ = ["storage_of"]
