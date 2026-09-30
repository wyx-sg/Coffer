"""Why the one-time upgrade to the vault layout refuses to run, or why the
daemon refuses to start on a home that has not taken it.

The move out of ``coffer.db`` is a step a person runs (``coffer migrate``),
never something the daemon does on its own (ADR
every-vault-file-carries-its-format-version "Rollback of a migration is a
restore, never a downgrade"), so every refusal names the command that
resolves it.
"""

from __future__ import annotations

from pathlib import Path

from coffer.domain.error_base import CofferError


class MigrationRequired(CofferError):  # noqa: N818
    """The home still holds the single database every build before the vault
    layout wrote, and no ``runs.db``: this build cannot read it."""

    code = "VAULT_MIGRATION_REQUIRED"

    def __init__(self, legacy_db: Path) -> None:
        super().__init__(
            f"{legacy_db} was written by a Coffer from before the vault layout. Stop the "
            "daemon and run `coffer migrate` once to move it into ~/.coffer/vault "
            "(`coffer migrate --rehearse` tries it on a copy first)."
        )


class MigrationOnHold(CofferError):  # noqa: N818
    """``coffer migrate --rollback`` put the home back and left its hold
    marker: this build neither starts on it nor migrates it again."""

    code = "VAULT_MIGRATION_ON_HOLD"

    def __init__(self, marker: Path) -> None:
        super().__init__(
            f"this home was rolled back to its pre-vault state ({marker} is present). "
            "Run the previous Coffer build, or run `coffer migrate --resume` and then "
            "`coffer migrate` to take the upgrade again."
        )


class PreVaultDatabase(CofferError):  # noqa: N818
    """A history database below the layout revision: its tables still hold
    the state that moves into files, and only ``coffer migrate`` moves it."""

    code = "VAULT_MIGRATION_REQUIRED"

    def __init__(self, db: str, revision: str) -> None:
        super().__init__(
            f"{db} is at revision {revision}, from before the vault layout; upgrading it "
            "here would drop tables whose state was never moved. Run `coffer migrate` "
            "against the home it came from."
        )


class MigrationRefused(CofferError):  # noqa: N818
    """``coffer migrate`` found a home it will not touch as it stands."""

    code = "VAULT_MIGRATION_REFUSED"


__all__ = ["MigrationOnHold", "MigrationRefused", "MigrationRequired", "PreVaultDatabase"]
