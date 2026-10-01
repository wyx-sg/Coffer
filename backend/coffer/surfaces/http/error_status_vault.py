"""HTTP statuses for the vault's and sync's error codes.

Split out of ``errors.py`` for the file-size tier: the vault layout and the
thin sync bring a family of codes of their own, and they read best together.
``errors._STATUS`` spreads this map into its own.
"""

from __future__ import annotations

VAULT_AND_SYNC_STATUS: dict[str, int] = {
    # The vault's write path (ADR every-vault-write-is-a-validated-commit-naming-its-writer).
    "VAULT_FILE_STALE": 409,
    "VAULT_FILE_INVALID": 422,
    "VAULT_PATH_INVALID": 400,
    "VAULT_VERSION_NOT_FOUND": 404,
    "VAULT_GIT_FAILED": 500,
    "GIT_MISSING": 500,
    "MASTER_KEY_FILE_INVALID": 422,
    "MASTER_KEY_PASSPHRASE_WRONG": 422,
    "MASTER_KEY_PASSPHRASE_TOO_SHORT": 422,
    # A round the user has to answer before anything else can happen. Each is
    # an ordinary state of the feature, not a fault: without an entry here they
    # fall through to 500, which tells a browser (and the CLI's exit-code
    # mapping) that Coffer broke when in fact it is waiting for an answer.
    "SYNC_NOTHING_TO_ROLL_BACK": 409,
    "SYNC_CANNOT_RETIRE_SELF": 422,
    # The thin sync round (spec vault-sync): no round waiting for this answer,
    # a hand merge that still has markers, a remote git would refuse, and a
    # remote that refused us (upstream, 502).
    "SYNC_NOTHING_STOPPED": 409,
    "SYNC_CONFLICT_MARKERS_LEFT": 422,
    "SYNC_SECRET_NOT_EDITABLE": 422,
    "SYNC_REMOTE_INVALID": 422,
    "SYNC_REMOTE_FAILED": 502,
    "SYNC_NO_REMOTE": 409,
    "SYNC_NO_PLAINTEXT_FOUND": 409,
    "SYNC_ROUND_NOT_FOUND": 404,
    "SYNC_MACHINE_NOT_FOUND": 404,
    "SYNC_MACHINE_NAME_INVALID": 422,
    "VAULT_MIGRATION_REQUIRED": 409,
    "VAULT_MIGRATION_ON_HOLD": 409,
    "VAULT_MIGRATION_REFUSED": 409,
}

__all__ = ["VAULT_AND_SYNC_STATUS"]
