"""Where the master key can live: the storage port and its backends.

ADR master-key-lives-in-the-macos-keychain. The key's store is a port
operation, not a macOS call spread through the code:

* :class:`KeychainAccessGroupBackend` — the release backend. One generic-password
  item in the macOS **data-protection** keychain, in an access group limited
  to Coffer's Team ID, with **no** user-presence flag, so the signed daemon
  reads it silently at every start (attended or not) while any other binary —
  an agent's program, ``/usr/bin/security`` — gets no access and no "Always
  Allow" dialog. Only a binary signed with the Developer ID and carrying the
  ``keychain-access-groups`` entitlement can use it; everything else gets
  ``errSecMissingEntitlement``.
* :class:`InMemoryMasterKeyBackend` — tests.

The ``0600`` file and the login-keychain item (through ``keyring``) stay
the development fallback, used only by a build that carries no access group:
see :func:`coffer.infrastructure.secret.build_identity.keychain_access_group`.
Which one a build uses is decided by how it was built, never by a setting or
an environment variable, so nothing an agent can write downgrades a release.
"""

from __future__ import annotations

import ctypes
import ctypes.util
from typing import Protocol

from coffer.domain.secret_errors import SecretLocked

SERVICE = "coffer"
ACCOUNT = "master-key"

#: OSStatus values the backend distinguishes.
ERR_SEC_SUCCESS = 0
ERR_SEC_ITEM_NOT_FOUND = -25300
ERR_SEC_DUPLICATE_ITEM = -25299
ERR_SEC_MISSING_ENTITLEMENT = -34018
ERR_SEC_INTERACTION_NOT_ALLOWED = -25308


class MasterKeyBackend(Protocol):
    """A place that holds at most one master key."""

    name: str

    def read(self) -> bytes | None:
        """The key, None when none is stored; ``SecretLocked`` when unreadable."""
        ...

    def write(self, key: bytes) -> None: ...

    def delete(self) -> None: ...


class InMemoryMasterKeyBackend:
    """A test double with the release backend's contract."""

    def __init__(self, name: str = "keychain_access_group") -> None:
        self.name = name
        self.key: bytes | None = None
        self.locked = False

    def read(self) -> bytes | None:
        if self.locked:
            raise SecretLocked("in-memory keychain is locked")
        return self.key

    def write(self, key: bytes) -> None:
        if self.locked:
            raise SecretLocked("in-memory keychain is locked")
        self.key = key

    def delete(self) -> None:
        self.key = None


class SecItemApi(Protocol):
    """The four Security.framework calls, over plain Python values."""

    def copy_matching(self, query: dict[str, object]) -> tuple[int, bytes | None]: ...
    def add(self, attributes: dict[str, object]) -> int: ...
    def update(self, query: dict[str, object], changes: dict[str, object]) -> int: ...
    def delete(self, query: dict[str, object]) -> int: ...


class KeychainAccessGroupBackend:
    """The master key as one data-protection Keychain item in Coffer's access group."""

    name = "keychain_access_group"

    def __init__(
        self, access_group: str, api: SecItemApi | None = None, *, account: str = ACCOUNT
    ) -> None:
        self._group = access_group
        self._account = account
        self._api = api if api is not None else _SecurityFramework()

    def _query(self) -> dict[str, object]:
        # No kSecAttrAccessControl: presence gates the operations that let
        # plaintext out, never the key the resident daemon reads unattended.
        return {
            "kSecClass": "kSecClassGenericPassword",
            "kSecAttrService": SERVICE,
            "kSecAttrAccount": self._account,
            "kSecAttrAccessGroup": self._group,
            "kSecUseDataProtectionKeychain": True,
        }

    def read(self) -> bytes | None:
        status, data = self._api.copy_matching(
            {**self._query(), "kSecReturnData": True, "kSecMatchLimit": "kSecMatchLimitOne"}
        )
        if status == ERR_SEC_ITEM_NOT_FOUND:
            return None
        if status != ERR_SEC_SUCCESS:
            raise SecretLocked(_describe(status))
        return data.strip() if data else None

    def write(self, key: bytes) -> None:
        status = self._api.add(
            {
                **self._query(),
                "kSecValueData": key,
                # Readable once the Mac has been unlocked after boot, so a
                # login service can start the daemon before anyone opens an
                # app; never synced to iCloud (ThisDeviceOnly).
                "kSecAttrAccessible": "kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly",
            }
        )
        if status == ERR_SEC_DUPLICATE_ITEM:
            status = self._api.update(self._query(), {"kSecValueData": key})
        if status != ERR_SEC_SUCCESS:
            raise SecretLocked(_describe(status))

    def delete(self) -> None:
        status = self._api.delete(self._query())
        if status not in (ERR_SEC_SUCCESS, ERR_SEC_ITEM_NOT_FOUND):
            raise SecretLocked(_describe(status))


def _describe(status: int) -> str:
    if status == ERR_SEC_MISSING_ENTITLEMENT:
        return (
            "this build is not signed into Coffer's Keychain access group "
            f"(errSecMissingEntitlement {status})"
        )
    if status == ERR_SEC_INTERACTION_NOT_ALLOWED:
        return f"the Keychain is not available yet — unlock this Mac once (OSStatus {status})"
    return f"the Keychain refused the master key item (OSStatus {status})"


class _SecurityFramework:
    """``SecItem*`` through ctypes, where Security.framework exists (macOS).

    Only a Developer-ID-signed binary with the access-group entitlement gets
    anything but ``errSecMissingEntitlement`` from these calls, so this code
    runs for real only in a signed release; tests inject a :class:`SecItemApi`.
    """

    def __init__(self) -> None:
        cf_path = ctypes.util.find_library("CoreFoundation")
        sec_path = ctypes.util.find_library("Security")
        if cf_path is None or sec_path is None:
            raise SecretLocked("Security.framework is not available on this host")
        self._cf = ctypes.cdll.LoadLibrary(cf_path)
        self._sec = ctypes.cdll.LoadLibrary(sec_path)
        vp = ctypes.c_void_p
        cf = self._cf
        cf.CFStringCreateWithCString.restype = vp
        cf.CFStringCreateWithCString.argtypes = [vp, ctypes.c_char_p, ctypes.c_uint32]
        cf.CFDataCreate.restype = vp
        cf.CFDataCreate.argtypes = [vp, ctypes.c_char_p, ctypes.c_long]
        cf.CFDataGetLength.restype = ctypes.c_long
        cf.CFDataGetLength.argtypes = [vp]
        cf.CFDataGetBytePtr.restype = ctypes.POINTER(ctypes.c_char)
        cf.CFDataGetBytePtr.argtypes = [vp]
        cf.CFDictionaryCreate.restype = vp
        cf.CFDictionaryCreate.argtypes = [
            vp,
            ctypes.POINTER(vp),
            ctypes.POINTER(vp),
            ctypes.c_long,
            vp,
            vp,
        ]
        cf.CFRelease.argtypes = [vp]
        for fn in ("SecItemCopyMatching", "SecItemAdd"):
            getattr(self._sec, fn).restype = ctypes.c_int32
            getattr(self._sec, fn).argtypes = [vp, ctypes.POINTER(vp)]
        self._sec.SecItemUpdate.restype = ctypes.c_int32
        self._sec.SecItemUpdate.argtypes = [vp, vp]
        self._sec.SecItemDelete.restype = ctypes.c_int32
        self._sec.SecItemDelete.argtypes = [vp]

    def _const(self, name: str) -> int:
        lib = self._cf if name.startswith("kCF") else self._sec
        return int(ctypes.c_void_p.in_dll(lib, name).value or 0)

    def _value(self, value: object, owned: list[int]) -> int:
        if value is True:
            return self._const("kCFBooleanTrue")
        if isinstance(value, bytes):
            ref = self._cf.CFDataCreate(None, value, len(value))
            owned.append(ref)
            return int(ref)
        text = str(value)
        if text.startswith("kSec"):
            return self._const(text)
        ref = self._cf.CFStringCreateWithCString(None, text.encode(), 0x08000100)  # UTF-8
        owned.append(ref)
        return int(ref)

    def _dict(self, items: dict[str, object], owned: list[int]) -> int:
        n = len(items)
        keys = (ctypes.c_void_p * n)(*[self._const(k) for k in items])
        values = (ctypes.c_void_p * n)(*[self._value(v, owned) for v in items.values()])
        ref = self._cf.CFDictionaryCreate(
            None,
            keys,
            values,
            n,
            ctypes.addressof(ctypes.c_void_p.in_dll(self._cf, "kCFTypeDictionaryKeyCallBacks")),
            ctypes.addressof(ctypes.c_void_p.in_dll(self._cf, "kCFTypeDictionaryValueCallBacks")),
        )
        owned.append(ref)
        return int(ref)

    def _release(self, owned: list[int]) -> None:
        for ref in owned:
            if ref:
                self._cf.CFRelease(ref)

    def copy_matching(self, query: dict[str, object]) -> tuple[int, bytes | None]:
        owned: list[int] = []
        try:
            out = ctypes.c_void_p()
            status = int(self._sec.SecItemCopyMatching(self._dict(query, owned), ctypes.byref(out)))
            if status != ERR_SEC_SUCCESS or not out.value:
                return status, None
            owned.append(out.value)
            length = self._cf.CFDataGetLength(out.value)
            return status, ctypes.string_at(self._cf.CFDataGetBytePtr(out.value), length)
        finally:
            self._release(owned)

    def add(self, attributes: dict[str, object]) -> int:
        owned: list[int] = []
        try:
            return int(self._sec.SecItemAdd(self._dict(attributes, owned), None))
        finally:
            self._release(owned)

    def update(self, query: dict[str, object], changes: dict[str, object]) -> int:
        owned: list[int] = []
        try:
            return int(
                self._sec.SecItemUpdate(self._dict(query, owned), self._dict(changes, owned))
            )
        finally:
            self._release(owned)

    def delete(self, query: dict[str, object]) -> int:
        owned: list[int] = []
        try:
            return int(self._sec.SecItemDelete(self._dict(query, owned)))
        finally:
            self._release(owned)
