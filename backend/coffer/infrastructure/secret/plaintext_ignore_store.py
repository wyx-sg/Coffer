"""``local/secret/plaintext-ignored.json`` (spec secret "Remember a value a
person says is not a secret"): the fingerprints of values a person said are
not secrets, machine-local and never synced. Holds no value."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from coffer.application.secret.plaintext_ignore import IgnoredValue
from coffer.infrastructure.vault.home import local_root
from coffer.infrastructure.vault.json_store import JsonStore


class JsonPlaintextIgnores:
    """Implements ``PlaintextIgnorePort``."""

    def __init__(self, path: Callable[[], Path] | None = None) -> None:
        self._store = JsonStore(
            path or (lambda: local_root() / "secret" / "plaintext-ignored.json")
        )

    def entries(self) -> tuple[IgnoredValue, ...]:
        out: list[IgnoredValue] = []
        for raw in self._store.read().get("values") or ():
            try:
                out.append(IgnoredValue(**raw))
            except TypeError:
                continue
        return tuple(out)

    def fingerprints(self) -> frozenset[str]:
        return frozenset(e.fingerprint for e in self.entries())

    def add(self, entries: Iterable[IgnoredValue]) -> None:
        new = list(entries)

        def change(doc: dict[str, Any]) -> None:
            kept = [v for v in doc.get("values") or () if isinstance(v, dict)]
            have = {v.get("fingerprint") for v in kept}
            for e in new:
                if e.fingerprint not in have:
                    kept.append(asdict(e))
                    have.add(e.fingerprint)
            doc["values"] = kept

        self._store.update(change)

    def remove(self, fingerprints: Iterable[str]) -> None:
        gone = set(fingerprints)

        def change(doc: dict[str, Any]) -> None:
            doc["values"] = [
                v
                for v in doc.get("values") or ()
                if isinstance(v, dict) and v.get("fingerprint") not in gone
            ]

        self._store.update(change)


__all__ = ["JsonPlaintextIgnores"]
