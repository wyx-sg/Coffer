"""The vault writer's refusals (spec vault-storage)."""

from __future__ import annotations

from coffer.domain.error_base import CofferError
from coffer.domain.vault.findings import Finding


class VaultFileStale(CofferError):  # noqa: N818
    """The file changed since the writer read it — by a person, an agent's
    file tools or another operation. Re-read and retry. Maps to 409."""

    code = "VAULT_FILE_STALE"

    def __init__(self, path: str, reason: str = "") -> None:
        self.path = path
        super().__init__(
            reason or f"{path} changed since it was read; read it again and retry the change"
        )


class VaultValidationFailed(CofferError):  # noqa: N818
    """A write would commit a file validation refuses; nothing was written.
    Maps to 422."""

    code = "VAULT_FILE_INVALID"

    def __init__(self, findings: list[Finding]) -> None:
        self.findings = findings
        first = findings[0] if findings else None
        detail = f"{first.path}: {first.message}" if first else "validation failed"
        more = f" (and {len(findings) - 1} more)" if len(findings) > 1 else ""
        super().__init__(detail + more)


class VaultPathRefused(CofferError):  # noqa: N818
    """A path that is not inside the vault, or that names ``.git``. Maps to 400."""

    code = "VAULT_PATH_INVALID"


__all__ = ["VaultFileStale", "VaultPathRefused", "VaultValidationFailed"]
