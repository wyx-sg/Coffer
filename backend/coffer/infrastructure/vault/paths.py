"""Mapping an absolute path onto the vault (file-system resolution, so not domain)."""

from __future__ import annotations

from pathlib import Path

from coffer.domain.vault.errors import VaultPathRefused
from coffer.domain.vault.writes import check_path


def vault_path(root: Path, absolute: Path) -> str:
    """``absolute`` as a vault-relative path; refuse one outside the vault."""
    try:
        rel = absolute.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise VaultPathRefused(f"{absolute} is not inside the vault") from exc
    return check_path(rel.as_posix())


__all__ = ["vault_path"]
