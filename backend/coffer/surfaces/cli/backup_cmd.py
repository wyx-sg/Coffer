"""coffer backup / restore — vault-level backup of Coffer's on-disk state.

These are offline, filesystem-only commands: they capture and re-place the
whole vault (``coffer.db`` + the knowledge / memory / skills markdown trees
under ``~/.coffer/``) without going through the daemon, so a backup is portable
and a restore works on a fresh machine before any daemon exists.

The markdown trees are the system of record; ``coffer.db`` is the rebuildable
index over them and is included so a restore is instant. The Fernet
``master.key`` is EXCLUDED by default — see ``--include-master-key`` — so a
backup stays safe to copy off-machine.
"""

from __future__ import annotations

from pathlib import Path

import typer

from coffer.infrastructure.vault import backup as _vault
from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._options import ExitCode

_MASTER_KEY_WARNING = (
    "WARNING: bundling master.key puts the credential-decryption key next to "
    "the encrypted credentials. Store this backup only where you'd store the "
    "live key — anyone with it can read every stored secret."
)


def _describe(manifest: _vault.BackupManifest) -> str:
    parts: list[str] = []
    if manifest.db:
        parts.append("coffer.db")
    parts.extend(manifest.trees)
    if manifest.master_key:
        parts.append("master.key")
    return ", ".join(parts) if parts else "(nothing)"


def backup(
    dest: str = typer.Argument(..., help="Destination .tar.gz file path for the backup"),
    include_master_key: bool = typer.Option(
        False,
        "--include-master-key",
        help=(
            "Also copy the Fernet master.key (UNSAFE — see warning). Without it, "
            "restored credentials must be re-entered or the key re-placed."
        ),
    ),
) -> None:
    """Write the live vault (db + file trees) into a ``.tar.gz`` archive at ``dest``.

    Excludes ``master.key`` unless ``--include-master-key`` is given, so the
    backup is safe to copy off-machine.
    """
    try:
        manifest = _vault.create_backup(
            Path(dest).expanduser(), include_master_key=include_master_key
        )
    except _vault.BackupError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(int(ExitCode.NOT_FOUND)) from None

    if manifest.master_key:
        typer.echo(_MASTER_KEY_WARNING, err=True)
    typer.echo(f"backup: {dest} [{_describe(manifest)}]")
    if not manifest.master_key:
        typer.echo(
            "note: master.key excluded — stored credentials need it to decrypt "
            "(re-enter them or re-place the key after restore).",
        )


def restore(
    src: str = typer.Argument(..., help="Backup .tar.gz file to restore from"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite a populated vault without prompting"
    ),
    reindex: bool = typer.Option(
        False,
        "--reindex",
        help="After restoring, rebuild the search index from the restored trees.",
    ),
) -> None:
    """Verify a backup and re-place its db + file trees into ``~/.coffer/``.

    Refuses to overwrite a non-empty vault unless ``--force`` (or an interactive
    confirmation) is given. The restored ``coffer.db`` is already a consistent
    index of the restored trees; pass ``--reindex`` to rebuild it anyway (e.g.
    after editing the trees by hand).
    """
    src_path = Path(src).expanduser()
    try:
        _vault.verify_backup(src_path)
    except _vault.BackupError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(int(ExitCode.INVALID_INPUT)) from None

    if (
        _vault.vault_is_populated()
        and not force
        and not typer.confirm(f"Vault at {_vault.vault_root()} already has data — overwrite it?")
    ):
        typer.echo("restore aborted", err=True)
        raise typer.Exit(int(ExitCode.GENERIC))

    try:
        manifest = _vault.restore_backup(src_path)
    except _vault.BackupError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(int(ExitCode.GENERIC)) from None
    typer.echo(f"restore: {_vault.vault_root()} [{_describe(manifest)}]")
    if not manifest.master_key:
        typer.echo(
            "note: master.key not in backup — re-place it to read stored "
            "credentials, or re-enter them via `coffer credentials set`.",
        )

    if reindex:
        _reindex_all()
    else:
        typer.echo("restored db is already a consistent index; run with --reindex to rebuild.")


def _reindex_all() -> None:
    """Rebuild the KB search index from the restored markdown trees (via daemon)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/knowledge_bases")
        if r.status_code != 200:
            typer.echo("could not list knowledge bases to reindex", err=True)
            return
        names = [kb["name"] for kb in r.json().get("knowledge_bases", [])]
        for name in names:
            rr = c.post(f"/knowledge_bases/{name}/reindex")
            status = "ok" if rr.status_code == 200 else f"failed ({rr.status_code})"
            typer.echo(f"reindex {name}: {status}")
    if not names:
        typer.echo("no knowledge bases to reindex")
