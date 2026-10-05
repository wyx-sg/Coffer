"""A ``JsonStore`` whose document carries an HMAC seal (the secret boundary's state).

The boundary's bindings, approvals and switches decide where a secret may go, so
a process that can only edit files (an agent running as the same user) must not
be able to change them. Each write adds ``"_seal"``: the hex HMAC-SHA256, under a
key derived from the master key, of the document's canonical JSON without the
seal. A read that finds a bad seal — or, in a signed build, no seal — treats the
file as empty and warns once; the next write reseals. A development build accepts
a file with no seal at all (an install from before sealing) and seals it on the
next write; a wrong seal is rejected in both. With no key yet there is nothing to
protect: nothing is sealed or checked.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
from collections.abc import Callable
from typing import Any

from coffer.infrastructure.vault.json_store import JsonStore

logger = logging.getLogger(__name__)

SEAL_FIELD = "_seal"
_WARNED: set[str] = set()
_WARNED_LOCK = threading.Lock()


def _seal(key: bytes, doc: dict[str, Any]) -> str:
    canonical = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()


class SealedJsonStore:
    def __init__(
        self,
        store: JsonStore,
        seal_key: Callable[[], bytes | None],
        *,
        development: bool,
    ) -> None:
        self._store = store
        self._seal_key = seal_key
        self._development = development

    def _warn(self) -> None:
        name = self._store.path.name
        with _WARNED_LOCK:
            if name in _WARNED:
                return
            _WARNED.add(name)
        logger.warning("secret_boundary.state_unsealed", extra={"file": name})

    def _trusted(self, raw: dict[str, Any], key: bytes | None) -> dict[str, Any]:
        seal = raw.get(SEAL_FIELD)
        body = {k: v for k, v in raw.items() if k != SEAL_FIELD}
        if key is None or not raw:
            return body
        if seal is None:
            if self._development:
                return body
        elif isinstance(seal, str) and hmac.compare_digest(seal, _seal(key, body)):
            return body
        self._warn()
        return {}

    def read(self) -> dict[str, Any]:
        return self._trusted(self._store.read(), self._seal_key())

    def update(self, change: Callable[[dict[str, Any]], None]) -> None:
        key = self._seal_key()

        def apply(raw: dict[str, Any]) -> dict[str, Any]:
            doc = self._trusted(raw, key)
            change(doc)
            if key is not None:
                doc[SEAL_FIELD] = _seal(key, {k: v for k, v in doc.items() if k != SEAL_FIELD})
            return doc

        self._store.update(apply)


__all__ = ["SealedJsonStore"]
