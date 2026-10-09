"""Delete Coffer's data from this machine (spec daemon "Uninstall Coffer from
this machine"; design D4 of ``add-self-update-and-uninstall``).

Run only once the daemon has stopped serving — by the daemon's own exit path
after it has released its lock, or by ``coffer uninstall --delete-data`` after
the daemon has exited — because ``~/.coffer`` holds the open history database
and the logs. In order:

1. the master key's Keychain items: in a signed release every item of Coffer's
   in its access group (the key and each ``master-key.bak-*``); in a
   development build the login-keychain item, when one was ever written;
2. ``~/.coffer`` itself. A vault moved elsewhere (``~/.coffer/vault`` is then a
   symlink) is not followed: the folder it points at may be shared or synced,
   so it is left in place and named in the result.
"""

from __future__ import annotations

import contextlib
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from coffer.infrastructure.secret.build_identity import keychain_access_group
from coffer.infrastructure.vault.home import coffer_home, vault_root

_logger = logging.getLogger(__name__)

#: The login-keychain ref a development build keeps the key under, when moved there.
_DEV_KEYRING_REF = "master-key"


@dataclass
class PurgeResult:
    removed: list[str] = field(default_factory=list)
    #: A moved vault's folder, left in place.
    kept: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


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
    root = coffer_home(home)
    vault = vault_root(home)
    if vault.is_symlink():
        with contextlib.suppress(OSError):
            result.kept.append(str(vault.resolve()))
    if root.exists():
        errors: list[str] = []
        shutil.rmtree(root, onexc=lambda _fn, path, exc: errors.append(f"{path}: {exc}"))
        result.errors.extend(errors)
        if not root.exists():
            result.removed.append(str(root))
    return result


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
