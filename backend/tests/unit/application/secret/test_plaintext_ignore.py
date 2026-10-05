"""Fingerprints and the machine-local ignore list (spec secret "Remember a value a
person says is not a secret")."""

from __future__ import annotations

import pathlib

from coffer.application.secret.plaintext_ignore import IgnoredValue, fingerprint, fingerprinter
from coffer.infrastructure.secret.plaintext_ignore_store import JsonPlaintextIgnores

VALUE = "Summer" + "2024!"


def _entry(fp: str) -> IgnoredValue:
    return IgnoredValue(fp, "r", "skills/a.sh", "K", "me", "2026-01-01T00:00:00+00:00")


def test_fingerprint_depends_on_key_and_value() -> None:
    a = fingerprint(b"k" * 32, VALUE)
    assert a == fingerprint(b"k" * 32, VALUE)
    assert a != fingerprint(b"j" * 32, VALUE) and a != fingerprint(b"k" * 32, VALUE + "x")
    assert VALUE not in a


def test_fingerprinter_without_a_key_gives_none() -> None:
    assert fingerprinter(lambda: None)(VALUE) is None
    assert fingerprinter(lambda: b"k" * 32)(VALUE) == fingerprint(b"k" * 32, VALUE)


def test_store_adds_once_and_removes(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "secret" / "ignored.json"
    store = JsonPlaintextIgnores(lambda: path)
    assert store.fingerprints() == frozenset()
    store.add([_entry("a"), _entry("b")])
    store.add([_entry("a")])
    assert store.fingerprints() == {"a", "b"} and len(store.entries()) == 2
    store.remove(["a"])
    assert store.fingerprints() == {"b"}
