"""The secret boundary's machine-local files (ADR storage-is-five-classes-by-nature;
spec credentials "Hold a secret for a new destination until a person approves it")."""

from __future__ import annotations

import base64
import json
import os
import pathlib
import stat
from concurrent.futures import ThreadPoolExecutor

import pytest

from coffer.domain.secrets import SecretApproval, SecretBinding
from coffer.infrastructure.credentials.boundary_store import FileBoundaryStore
from coffer.infrastructure.vault.home import local_root, vault_root


def _approval(approval_id: str, created_at: str, **kw: object) -> SecretApproval:
    fields: dict[str, object] = {
        "op": "bind",
        "status": "pending",
        "requested_by": "user",
        "ref": "gh/token",
        "destination_kind": "mcp_server",
        "destination_uid": "u1",
        "destination_label": "github",
        "slot": "TOKEN",
        "target": "npx server",
        "target_fingerprint": "fp1",
    }
    fields.update(kw)
    return SecretApproval(id=approval_id, created_at=created_at, **fields)  # type: ignore[arg-type]


def _binding(ref: str = "gh/token", slot: str = "TOKEN", fp: str = "fp1") -> SecretBinding:
    return SecretBinding(
        ref=ref,
        destination_kind="mcp_server",
        destination_uid="u1",
        slot=slot,
        target_fingerprint=fp,
        approved_at="2026-09-30T00:00:00+00:00",
        approval_id=None,
    )


@pytest.fixture
def store(tmp_path: pathlib.Path) -> FileBoundaryStore:
    return FileBoundaryStore(tmp_path)


def _secrets(tmp_path: pathlib.Path) -> pathlib.Path:
    return local_root(tmp_path) / "secret-boundary"


def test_bindings_upsert_on_their_key_and_are_listed_in_order(
    store: FileBoundaryStore, tmp_path: pathlib.Path
) -> None:
    store.put_binding(_binding(slot="B"))
    store.put_binding(_binding(slot="A"))
    store.put_binding(_binding(slot="B", fp="fp2"))
    store.put_binding(_binding(ref="other/ref"))

    assert [(b.ref, b.slot) for b in store.bindings()] == [
        ("gh/token", "A"),
        ("gh/token", "B"),
        ("other/ref", "TOKEN"),
    ]
    got = store.get_binding("gh/token", "mcp_server", "u1", "B")
    assert got is not None and got.target_fingerprint == "fp2"
    assert store.has_any_binding("other/ref")
    store.delete_bindings("gh/token")
    assert [b.ref for b in store.bindings()] == ["other/ref"]
    assert store.get_binding("gh/token", "mcp_server", "u1", "A") is None
    doc = json.loads((_secrets(tmp_path) / "bindings.json").read_text())
    assert [b["ref"] for b in doc["bindings"]] == ["other/ref"]


def test_state_is_local_and_never_in_the_vault(
    store: FileBoundaryStore, tmp_path: pathlib.Path
) -> None:
    store.put_binding(_binding())
    store.create_approval(_approval("a1", "2026-09-30T01:00:00"), b"sealed")
    store.set_setting("require_approval", "true")
    for name in ("bindings.json", "approvals.json", "settings.json"):
        path = _secrets(tmp_path) / name
        assert path.is_file()
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert not vault_root(tmp_path).exists()


def test_a_pending_replacement_keeps_its_ciphertext_base64_until_decided(
    store: FileBoundaryStore, tmp_path: pathlib.Path
) -> None:
    sealed = b"gAAAAB-ciphertext\x00\xff"
    store.create_approval(_approval("a1", "2026-09-30T01:00:00", op="replace_value"), sealed)
    raw = json.loads((_secrets(tmp_path) / "approvals.json").read_text())
    assert raw["approvals"][0]["pending_ciphertext"] == base64.b64encode(sealed).decode()
    assert store.pending_ciphertext("a1") == sealed

    assert store.decide("a1", "approved", by="user", at="2026-09-30T02:00:00") is True
    assert store.pending_ciphertext("a1") is None
    decided = store.get_approval("a1")
    assert decided is not None
    assert (decided.status, decided.decided_by, decided.decided_at) == (
        "approved",
        "user",
        "2026-09-30T02:00:00",
    )


def test_decide_is_a_compare_and_set_on_pending(store: FileBoundaryStore) -> None:
    store.create_approval(_approval("a1", "2026-09-30T01:00:00"))
    assert store.decide("a1", "rejected", by="first", at="t1") is True
    assert store.decide("a1", "approved", by="second", at="t2") is False
    assert store.decide("missing", "approved", by="x", at="t") is False
    decided = store.get_approval("a1")
    assert decided is not None and (decided.status, decided.decided_by) == ("rejected", "first")


def test_concurrent_answers_to_one_approval_take_effect_once(store: FileBoundaryStore) -> None:
    store.create_approval(_approval("a1", "2026-09-30T01:00:00"))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(lambda i: store.decide("a1", "approved", by=f"p{i}", at="t"), range(16))
        )
    assert results.count(True) == 1


def test_an_approval_id_is_created_once(store: FileBoundaryStore) -> None:
    store.create_approval(_approval("a1", "2026-09-30T01:00:00"))
    with pytest.raises(ValueError):
        store.create_approval(_approval("a1", "2026-09-30T01:00:01"))


def test_queries_over_approvals(store: FileBoundaryStore) -> None:
    store.create_approval(_approval("a1", "2026-09-30T01:00:00"))
    store.create_approval(_approval("a2", "2026-09-30T03:00:00", status="rejected"))
    store.create_approval(_approval("a3", "2026-09-30T02:00:00", destination_uid="u2"))
    store.create_approval(
        _approval("a4", "2026-09-30T04:00:00", op="replace_value", ref="other/ref")
    )

    assert [a.id for a in store.list_approvals()] == ["a4", "a2", "a3", "a1"]
    assert [a.id for a in store.list_approvals(status="pending", limit=2)] == ["a4", "a3"]
    assert [a.id for a in store.list_approvals(destination_uid="u2")] == ["a3"]
    assert {a.id for a in store.pending_of_op("bind")} == {"a1", "a3"}
    assert [a.id for a in store.pending_of_op("replace_value", "other/ref")] == ["a4"]
    assert store.pending_of_op("replace_value", "gh/token") == []
    # The newest pending-or-refused bind for exactly this binding and target.
    found = store.find_open_bind("gh/token", "mcp_server", "u1", "TOKEN", "fp1")
    assert found is not None and found.id == "a2"
    assert store.find_open_bind("gh/token", "mcp_server", "u1", "TOKEN", "other-fp") is None
    assert store.get_approval("nope") is None


def test_settings_round_trip(store: FileBoundaryStore) -> None:
    assert store.get_setting("require_approval") is None
    store.set_setting("require_approval", "false")
    store.set_setting("adopted_existing_bindings", "true")
    assert store.get_setting("require_approval") == "false"
    assert store.get_setting("adopted_existing_bindings") == "true"
