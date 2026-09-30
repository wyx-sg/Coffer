"""Every path directly under ``~/.coffer`` — the only module that knows them.

The five class directories (ADR storage-is-five-classes-by-nature) and the
runtime files beside them are all named here and nowhere else;
``scripts/check_coffer_paths.py`` (in ``make lint``) fails on a ``".coffer"``
built anywhere else in ``backend/coffer/``. What lives *inside* a class
directory is its owner's business (``knowledge/paths.py``, ``memory/paths.py``
…), reached from the root this module returns.

Every path is resolved from ``HOME`` at the moment it is asked for, never
cached, so a test (or a rehearsal of the migration in a throwaway home) that
repoints ``HOME`` moves every class with it. There is deliberately no per-tree
override: the knowledge collections and the skill master folders are inside
the vault repository, and a tree outside it would be a tree git cannot see.
The overrides that do exist (``COFFER_LOG_DIR``, ``COFFER_PROXY_SPOOL_DIR``,
``COFFER_SEATALK_SDK_DIR``, ``COFFER_EVAL_CAPTURE``) replace a whole path and
are read by the module that owns the path; the default each falls back to is
here.

``daemon-config.json`` and ``daemon.json`` stay directly under ``~/.coffer``:
the first is read before any migration can run (it carries the port the daemon
binds), the second is the rendezvous every surface reads to find the running
daemon. Neither is stored state of any class. The same holds for the other
runtime files named below: the spawn lock, the model proxy's ``proxy.json``
and usage spool, the upstream pid files, the logs and the deployed binaries.
"""

from __future__ import annotations

import os
from pathlib import Path

#: The spool directory the model proxy appends usage records to.
PROXY_USAGE_DIRNAME = "proxy-usage"
#: Where the running model proxy publishes ``{port, pid, started_at, version,
#: control_token}`` (mode 0600), beside ``daemon.json``.
PROXY_INFO_FILENAME = "proxy.json"
#: The fallback machine identifier a host with none of its own gets, written
#: once (mode 0600) beside ``daemon.json`` (spec vault-sync "Keep machine
#: identity across reinstalls").
MACHINE_ID_FILENAME = "machine-id"


def coffer_home(home: Path | None = None) -> Path:
    """``~/.coffer`` for ``home`` (default: this process's ``HOME``)."""
    base = home if home is not None else Path(os.environ.get("HOME", "~")).expanduser()
    return base / ".coffer"


def vault_root(home: Path | None = None) -> Path:
    """The vault repository: configuration and content, the only copy."""
    return coffer_home(home) / "vault"


def local_root(home: Path | None = None) -> Path:
    """Machine-local state: never synced, can be set again."""
    return coffer_home(home) / "local"


def content_root(home: Path | None = None) -> Path:
    """Media and the chat workspace: the user's only copy, not synced yet."""
    return coffer_home(home) / "content"


def derived_root(home: Path | None = None) -> Path:
    """Rebuilt from other state; deleting it is always safe."""
    return coffer_home(home) / "derived"


def runs_db_path(home: Path | None = None) -> Path:
    """The history database: audit, invocations, conversations, rounds, usage."""
    return coffer_home(home) / "runs.db"


def legacy_db_path(home: Path | None = None) -> Path:
    """The single database every build before the vault layout wrote."""
    return coffer_home(home) / "coffer.db"


def daemon_json_path(home: Path | None = None) -> Path:
    """The running daemon's rendezvous file: port, pid and bearer token."""
    return coffer_home(home) / "daemon.json"


def daemon_config_path(home: Path | None = None) -> Path:
    """The machine's own settings, read before the database opens."""
    return coffer_home(home) / "daemon-config.json"


def daemon_lock_path(home: Path | None = None) -> Path:
    """The ``flock`` that serialises two processes spawning a daemon at once."""
    return coffer_home(home) / "daemon.lock"


def logs_dir(home: Path | None = None) -> Path:
    """Where the daemon, the shims and the upstream servers log."""
    return coffer_home(home) / "logs"


def bin_dir(home: Path | None = None) -> Path:
    """Where the frozen binaries are deployed (the public names and versions)."""
    return coffer_home(home) / "bin"


def master_key_path(home: Path | None = None) -> Path:
    """The development key file that opens the vault's ciphertext."""
    return coffer_home(home) / "master.key"


def legacy_secrets_dir(home: Path | None = None) -> Path:
    """The plain key files skills read before ``coffer run --secret``."""
    return coffer_home(home) / "secrets"


def upstream_pids_dir(home: Path | None = None) -> Path:
    """One pid file per spawned upstream MCP server, for the orphan sweep."""
    return coffer_home(home) / "upstream-pids"


def vendor_dir(home: Path | None = None) -> Path:
    """Operator-supplied packages Coffer does not ship (the SeaTalk SDK)."""
    return coffer_home(home) / "vendor"


def eval_capture_path(home: Path | None = None) -> Path:
    """The default JSONL sink when eval capture is switched on."""
    return coffer_home(home) / "eval-capture.jsonl"


def proxy_info_path(home: Path | None = None) -> Path:
    """The running model proxy's ``proxy.json``."""
    return coffer_home(home) / PROXY_INFO_FILENAME


def proxy_usage_dir(home: Path | None = None) -> Path:
    """The model proxy's usage spool."""
    return coffer_home(home) / PROXY_USAGE_DIRNAME


__all__ = [
    "MACHINE_ID_FILENAME",
    "PROXY_INFO_FILENAME",
    "PROXY_USAGE_DIRNAME",
    "bin_dir",
    "coffer_home",
    "content_root",
    "daemon_config_path",
    "daemon_json_path",
    "daemon_lock_path",
    "derived_root",
    "eval_capture_path",
    "legacy_db_path",
    "legacy_secrets_dir",
    "local_root",
    "logs_dir",
    "master_key_path",
    "proxy_info_path",
    "proxy_usage_dir",
    "runs_db_path",
    "upstream_pids_dir",
    "vault_root",
    "vendor_dir",
]
