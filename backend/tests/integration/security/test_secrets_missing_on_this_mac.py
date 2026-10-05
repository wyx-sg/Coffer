"""Secrets this Mac cannot open, when each secret was used, and a plaintext move that
could not rewrite its file — against a real in-process daemon over a throwaway HOME
(spec secret)."""

from __future__ import annotations

import pathlib
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet

from coffer.domain.vault.layout import SECRET
from coffer.infrastructure.secret.ref_paths import ref_to_relpath
from coffer.infrastructure.vault.home import vault_root
from coffer.surfaces.http import reconcile_dependencies
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
    """A ciphertext file that came with the vault from a Mac holding another
    master key (ADR storage-is-five-classes-by-nature: ``vault/secret/<ref>.enc``)."""
    blob = Fernet(Fernet.generate_key()).encrypt(b"from-the-other-mac")
    path = vault_root(d.home) / SECRET / ref_to_relpath(ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob + b"\n")
    # The sync round that brings such a file ends with a reconcile pass, whose
    # nudge drops the kept attention list; planting it by hand skips that.
    reconcile_dependencies.get_attention_service().invalidate()


@pytest.mark.acceptance(
    spec="secret", scenario="a ciphertext from another Mac's key is listed as locked"
)
def test_a_ciphertext_from_another_key_is_listed_as_locked(d: BoundaryDaemon) -> None:
    _plant_foreign_ciphertext(d, "secret/sentry-token")
    d.store("secret/github-token", "ghp_this_mac")
    before = len(d.audit_all())

    rows = _listed(d)

    assert rows["secret/sentry-token"]["present"] is True
    assert rows["secret/sentry-token"]["locked"] is True
    assert rows["secret/github-token"]["locked"] is False
    # Listing decrypts nothing and audits nothing.
    assert len(d.audit_all()) == before


@pytest.mark.acceptance(
    spec="secret", scenario="a value added for a locked secret replaces it at once"
)
def test_a_value_added_for_a_locked_secret_replaces_it_at_once(d: BoundaryDaemon) -> None:
    _plant_foreign_ciphertext(d, "secret/sentry-token")

    r = d.client.post("/api/v1/secrets", json={"ref": "secret/sentry-token", "value": "sntrys_new"})

    assert r.status_code == 204, r.text
    assert d.pending() == []
    assert _listed(d)["secret/sentry-token"]["locked"] is False
    assert d.value("secret/sentry-token") == "sntrys_new"


@pytest.mark.acceptance(
    spec="secret", scenario="the list says when each secret was created and last used"
)
def test_the_list_says_when_each_secret_was_created_and_last_used(d: BoundaryDaemon) -> None:
    d.store("secret/db-password", "correct-horse-battery")
    row = _listed(d)["secret/db-password"]
    assert row["created_at"] and row["last_used_at"] is None

    d.grant_local("db-password")
    r = d.client.post(
        "/api/v1/secrets/resolve",
        json={"names": ["db-password"], "argv0": "psql", "cwd": "/tmp"},
    )
    assert r.status_code == 200, r.text

    used = _listed(d)["secret/db-password"]["last_used_at"]
    assert isinstance(used, str)
    assert datetime.fromisoformat(used) <= datetime.now(tz=UTC)


@pytest.mark.acceptance(
    spec="secret", scenario="a dot-only segment is refused rather than answered with a server error"
)
def test_a_dot_only_ref_segment_is_refused_not_answered_with_a_500(d: BoundaryDaemon) -> None:
    """``.`` and ``..`` pass a character-class check but name no file."""
    for ref in ("..", "a/../b", "."):
        r = d.client.post("/api/v1/secrets", json={"ref": ref, "value": "x"})
        assert r.status_code == 422, (ref, r.text)
    # Over the path routes the segment arrives percent-encoded.
    assert d.client.get("/api/v1/secrets/%2E%2E/exists").status_code == 422
    assert d.client.delete("/api/v1/secrets/a/%2E%2E").status_code == 422


def _attention(d: BoundaryDaemon) -> dict[str, object]:
    r = d.client.get("/api/v1/attention")
    assert r.status_code == 200, r.text
    return r.json()


def _secret_items(report: dict[str, object], field: str = "items") -> dict[str, dict[str, object]]:
    return {i["reason_code"]: i for i in report[field] if i["kind"] == "secret"}  # type: ignore[attr-defined]


@pytest.mark.acceptance(
    spec="secret", scenario="secrets with no value on this Mac are listed on Overview"
)
def test_a_secret_with_no_value_here_is_on_overview_and_counts_toward_the_badge(
    d: BoundaryDaemon,
) -> None:
    assert "secret_missing_here" not in _secret_items(_attention(d))
    _plant_foreign_ciphertext(d, "secret/sentry-token")

    report = _attention(d)

    item = _secret_items(report)["secret_missing_here"]
    assert item["severity"] == "error"
    assert item["reason"] == "1 secret has no value on this Mac."
    assert report["counts_by_kind"]["secret"] == 1  # type: ignore[index]


@pytest.mark.acceptance(
    spec="secret", scenario="an ignored secret item returns when the situation changes"
)
def test_an_ignored_missing_secret_item_returns_when_another_goes_missing(
    d: BoundaryDaemon,
) -> None:
    _plant_foreign_ciphertext(d, "secret/sentry-token")
    key = str(_secret_items(_attention(d))["secret_missing_here"]["key"])

    assert d.client.put(f"/api/v1/attention/ignored/{key}").status_code < 300
    ignored = _attention(d)
    assert "secret_missing_here" not in _secret_items(ignored)
    assert "secret_missing_here" in _secret_items(ignored, "ignored")
    assert "secret" not in ignored["counts_by_kind"]  # type: ignore[operator]

    _plant_foreign_ciphertext(d, "secret/other-token")
    back = _secret_items(_attention(d))["secret_missing_here"]
    assert back["key"] != key
    assert back["reason"] == "2 secrets have no value on this Mac."
