"""Secrets this Mac cannot open, when each secret was used, and a plaintext move that
could not rewrite its file — against a real in-process daemon over a throwaway HOME
(spec secret)."""

from __future__ import annotations

import pathlib
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet

from tests.support.boundary_daemon import BoundaryDaemon, prepare_home, running_daemon


@pytest.fixture
def d(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as daemon:
        yield daemon


def _listed(d: BoundaryDaemon) -> dict[str, dict[str, object]]:
    r = d.client.get("/api/v1/secrets")
    assert r.status_code == 200, r.text
    return {row["ref"]: row for row in r.json()["refs"]}


def _plant_foreign_ciphertext(d: BoundaryDaemon, ref: str) -> None:
    """A row that came with the vault from a Mac holding another master key."""
    now = datetime.now(tz=UTC).isoformat()
    blob = Fernet(Fernet.generate_key()).encrypt(b"from-the-other-mac")
    d.sql(
        "INSERT INTO secrets (ref, ciphertext, created_at, updated_at) VALUES (?, ?, ?, ?)",
        ref,
        blob,
        now,
        now,
    )


@pytest.mark.acceptance(
    spec="secret", scenario="a ciphertext from another Mac's key is listed as locked"
)
def test_a_ciphertext_from_another_key_is_listed_as_locked(d: BoundaryDaemon) -> None:
    _plant_foreign_ciphertext(d, "secret/sentry-token")
    d.store("secret/github-token", "ghp_this_mac")
    before = len(d.audit("secret_read")) + len(d.audit("secret_revealed"))

    rows = _listed(d)

    assert rows["secret/sentry-token"]["present"] is True
    assert rows["secret/sentry-token"]["locked"] is True
    assert rows["secret/github-token"]["locked"] is False
    # Listing decrypts nothing and audits nothing.
    assert len(d.audit("secret_read")) + len(d.audit("secret_revealed")) == before


@pytest.mark.acceptance(
    spec="secret", scenario="a value added for a locked secret replaces it once approved"
)
def test_a_value_added_for_a_locked_secret_replaces_it_once_approved(d: BoundaryDaemon) -> None:
    _plant_foreign_ciphertext(d, "secret/sentry-token")

    r = d.client.post("/api/v1/secrets", json={"ref": "secret/sentry-token", "value": "sntrys_new"})

    assert r.status_code == 202, r.text
    approval = r.json()["approval"]
    assert approval["op"] == "replace_value"
    assert _listed(d)["secret/sentry-token"]["locked"] is True
    d.approve(approval["id"])
    assert _listed(d)["secret/sentry-token"]["locked"] is False
    assert d.value("secret/sentry-token") == "sntrys_new"


@pytest.mark.acceptance(
    spec="secret", scenario="the list says when each secret was created and last used"
)
def test_the_list_says_when_each_secret_was_created_and_last_used(d: BoundaryDaemon) -> None:
    d.store("secret/db-password", "correct-horse-battery")
    row = _listed(d)["secret/db-password"]
    assert row["created_at"] and row["last_used_at"] is None

    r = d.client.post(
        "/api/v1/secrets/resolve",
        json={"names": ["db-password"], "argv0": "psql", "cwd": "/tmp"},
    )
    assert r.status_code == 200, r.text

    used = _listed(d)["secret/db-password"]["last_used_at"]
    assert isinstance(used, str)
    assert datetime.fromisoformat(used) <= datetime.now(tz=UTC)


@pytest.mark.acceptance(
    spec="secret", scenario="a file that cannot be rewritten keeps its key and says so"
)
def test_a_file_that_cannot_be_rewritten_keeps_its_key_and_says_so(d: BoundaryDaemon) -> None:
    secrets = d.home / ".coffer" / "secrets"
    secrets.mkdir(parents=True, exist_ok=True)
    env = secrets / "aws.env"
    env.write_text("AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY\n")
    before = env.read_text()
    secrets.chmod(0o500)
    try:
        r = d.client.post("/api/v1/secrets/import", json={})
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["moved"] == []
        [skipped] = out["skipped"]
        assert skipped["stored"] is True and skipped["name"] == "aws.AWS_SECRET_ACCESS_KEY"
        assert "couldn't be rewritten" in skipped["reason"]
        assert env.read_text() == before
        assert d.value("secret/aws.AWS_SECRET_ACCESS_KEY") is not None
        assert [e["details"]["name"] for e in d.audit("secret_imported")] == [
            "aws.AWS_SECRET_ACCESS_KEY"
        ]
    finally:
        secrets.chmod(0o700)

    again = d.client.post("/api/v1/secrets/import", json={"ids": [skipped["id"]]})
    assert again.status_code == 200, again.text
    assert [m["name"] for m in again.json()["moved"]] == ["aws.AWS_SECRET_ACCESS_KEY"]
    assert "coffer://secret/aws.AWS_SECRET_ACCESS_KEY" in env.read_text()


@pytest.mark.acceptance(
    spec="secret", scenario="a scan that finds nothing says how many files it read"
)
def test_a_scan_that_finds_nothing_says_how_many_files_it_read(d: BoundaryDaemon) -> None:
    secrets = d.home / ".coffer" / "secrets"
    secrets.mkdir(parents=True, exist_ok=True)
    (secrets / "empty.env").write_text("# nothing here\n")

    r = d.client.post("/api/v1/secrets/scan")

    assert r.status_code == 200, r.text
    assert r.json()["findings"] == []
    assert r.json()["files_checked"] >= 1
