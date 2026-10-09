"""Delete Coffer's data from this machine (spec daemon "Uninstall Coffer from
this machine"; design D4 of ``add-self-update-and-uninstall``).

Run by the daemon's own exit path once it has stopped serving and released its
lock, because ``~/.coffer`` holds the open history database and the logs. In
order:

1. the master key's Keychain items: in a signed release every item of Coffer's
   in its access group (the key and each ``master-key.bak-*``); in a
   development build the login-keychain item, when one was ever written;
2. ``~/.coffer`` itself (``data_files.py``, which ``coffer uninstall
   --delete-data`` runs on its own: the command line never touches the
   Keychain).
"""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path

from coffer.infrastructure.daemon.data_files import PurgeResult, purge_files
from coffer.infrastructure.secret.build_identity import keychain_access_group

_logger = logging.getLogger(__name__)

#: The login-keychain ref a development build keeps the key under, when moved there.
_DEV_KEYRING_REF = "master-key"


def _delete_keychain_items() -> str:
    group = keychain_access_group()
    if group:
        from coffer.infrastructure.secret.master_key_backends import KeychainAccessGroupBackend

        KeychainAccessGroupBackend(group).delete_all()
        return f"Keychain items in {group}"
    from coffer.infrastructure.secret.keyring_adapter import KeyringAdapter

    with contextlib.suppress(Exception):
        KeyringAdapter().delete(_DEV_KEYRING_REF)
    return "the development master key's login-keychain item"


def purge_data(home: Path | None = None, *, keychain: bool = True) -> PurgeResult:
    """Delete the master key's Keychain items, then ``~/.coffer``. Every part is
    attempted; failures are collected, never raised."""
    result = PurgeResult()
    if keychain:
        try:
            result.removed.append(_delete_keychain_items())
        except Exception as exc:
            result.errors.append(f"Keychain: {exc}")
    return purge_files(home, result)


# --- the daemon's purge at exit ----------------------------------------------------

_purge_on_exit = False


def purge_on_exit() -> None:
    """Have the daemon's exit path purge the data once it has stopped serving."""
    global _purge_on_exit
    _purge_on_exit = True


def purge_if_requested() -> PurgeResult | None:
    """The daemon's exit path: the purge an uninstall asked for, if one did."""
    if not _purge_on_exit:
        return None
    result = purge_data()
    # The log file is gone with ~/.coffer; stderr reaches whatever started us.
    print(
        f"coffer: deleted {', '.join(result.removed) or 'nothing'}"
        + (f"; kept {', '.join(result.kept)}" if result.kept else "")
        + (f"; failed: {'; '.join(result.errors)}" if result.errors else ""),
        flush=True,
    )
    return result


__all__ = ["PurgeResult", "purge_data", "purge_if_requested", "purge_on_exit"]
