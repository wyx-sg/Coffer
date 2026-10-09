"""The daemon proves it is Coffer's, and installing a master key needs a person
(spec secret "Release plaintext only to a present human in the desktop app").

The shell's half is played with the same derivation it uses: the attest key and
the grant key come from the daemon's own master key.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet

from coffer.application.secret.presence import attest, derive_purpose_key
from coffer.domain.secrets import DAEMON_ATTEST_KEY_CONTEXT
from coffer.infrastructure.secret import key_backup
from coffer.surfaces.http import daemon_port
from coffer.surfaces.http.secret_composition import get_master_key_manager
from tests.support.boundary_daemon import BoundaryDaemon, prepare_home, running_daemon

MASTER = b"ZmFrZS1tYXN0ZXIta2V5LWZvci10ZXN0cy0wMDAwMDA="
ATTEST_URL = "/api/v1/secrets/presence/attest"
IMPORT_URL = "/api/v1/secrets/key/import"


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as d:
        yield d


def test_the_attest_key_and_signature_match_the_shells_vectors() -> None:
    key = derive_purpose_key(MASTER, DAEMON_ATTEST_KEY_CONTEXT)
    assert key.hex() == "1037a277fa914a1ae40b22967caeb076bba99cc8f5ada5ce47fce7f1a04f4e63"
    assert (
        attest(key, "nonce-123")
        == "9ea1bd3ea31d3819392c1a1ab7d367b01d1595860e08189d9dce98c9216fe23b"
    )


def test_the_daemon_answers_a_challenge_bound_to_the_port_it_serves(
    daemon: BoundaryDaemon,
) -> None:
    nonce = "n" * 24
    r = daemon.client.post(ATTEST_URL, json={"nonce": nonce})
    assert r.status_code == 200, r.text
    key = derive_purpose_key(get_master_key_manager().current or b"", DAEMON_ATTEST_KEY_CONTEXT)
    port = daemon_port.get_port()
    assert r.json()["signature"] == attest(key, f"{nonce}\n{port}")
    # The same nonce at another port is another answer: a relayed reply is useless.
    assert r.json()["signature"] != attest(key, f"{nonce}\n{port + 1}")


def test_a_challenge_needs_the_token_and_a_well_formed_nonce(daemon: BoundaryDaemon) -> None:
    assert daemon.client.post(ATTEST_URL, json={"nonce": "short"}).status_code == 422
    assert daemon.client.post(ATTEST_URL, json={"nonce": "has space " * 3}).status_code == 422
    bare = daemon.client.post(ATTEST_URL, json={"nonce": "n" * 24}, headers={"X-Coffer-Token": ""})
    assert bare.status_code in (401, 403)


# --- importing a master key ---------------------------------------------------------


def _new_key() -> str:
    return Fernet.generate_key().decode()


def _import(d: BoundaryDaemon, material: str, grant: dict[str, str]) -> object:
    return d.client.post(IMPORT_URL, json={"material": material, **grant})


def _fingerprint_of(d: BoundaryDaemon, material: str) -> str:
    r = d.client.post("/api/v1/secrets/key/import/preview", json={"material": material})
    assert r.status_code == 200, r.text
    return str(r.json()["fingerprint"])


def test_a_key_import_without_a_grant_changes_nothing(daemon: BoundaryDaemon) -> None:
    before = get_master_key_manager().current
    r = daemon.client.post(IMPORT_URL, json={"material": _new_key()})
    assert r.status_code == 422
    forged = daemon.client.post(
        IMPORT_URL, json={"material": _new_key(), "nonce": "x" * 16, "signature": "0" * 64}
    )
    assert forged.status_code == 403
    assert get_master_key_manager().current == before


def test_a_grant_for_another_fingerprint_does_not_import(daemon: BoundaryDaemon) -> None:
    before = get_master_key_manager().current
    wanted, other = _new_key(), _new_key()
    grant = daemon.grant("import_master_key", _fingerprint_of(daemon, other))
    r = _import(daemon, wanted, grant)
    assert r.status_code == 403  # type: ignore[attr-defined]
    assert get_master_key_manager().current == before


def test_a_valid_grant_imports_once_and_the_audit_names_the_desktop(
    daemon: BoundaryDaemon,
) -> None:
    key = _new_key()
    fingerprint = _fingerprint_of(daemon, key)
    grant = daemon.grant("import_master_key", fingerprint)
    r = _import(daemon, key, grant)
    assert r.status_code == 200, r.text  # type: ignore[attr-defined]
    assert r.json()["fingerprint"] == fingerprint  # type: ignore[attr-defined]
    assert get_master_key_manager().current == key.encode()
    assert [e["actor"] for e in daemon.audit("master_key_imported")] == ["desktop"]
    # The nonce is spent: replaying the same request installs nothing.
    again = _import(daemon, _new_key(), grant)
    assert again.status_code == 403  # type: ignore[attr-defined]
    assert get_master_key_manager().current == key.encode()


def test_a_protected_backup_is_granted_by_the_fingerprint_in_the_file(
    daemon: BoundaryDaemon,
) -> None:
    key = _new_key()
    backup = key_backup.wrap(key.encode(), "correct horse battery")
    fingerprint = _fingerprint_of(daemon, backup)
    assert fingerprint == key_backup.key_fingerprint(key.encode())
    grant = daemon.grant("import_master_key", fingerprint)
    r = daemon.client.post(
        IMPORT_URL, json={"material": backup, "passphrase": "correct horse battery", **grant}
    )
    assert r.status_code == 200, r.text
    assert get_master_key_manager().current == key.encode()
