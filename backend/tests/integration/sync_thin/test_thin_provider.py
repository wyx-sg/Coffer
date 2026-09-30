"""A provider connection travels between machines as its own vault file
(spec provider-switching "Converge connections across machines"): the file
arrives byte for byte, its secret only as ciphertext and only when the remote
carries secrets, and a later edit follows the same way."""

from __future__ import annotations

import base64
import struct
from pathlib import Path

import pytest

from coffer.application.sync.round_join import join
from coffer.domain.sync.remote import SyncRemote

from .machines import Machine, bare_remote, resource


def _fernet(when: int, payload: bytes = b"x" * 32) -> bytes:
    raw = bytes([0x80]) + struct.pack(">Q", when) + payload
    return base64.urlsafe_b64encode(raw) + b"\n"


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a provider profile round-trips through sync export and import",
)
def test_a_connection_travels_as_its_file_with_its_ciphertext(tmp_path: Path) -> None:
    carried = SyncRemote(url=str(bare_remote(tmp_path)), include_secret=True)
    mac = Machine(tmp_path / "mac", "MacBook Pro", carried)
    mini = Machine(tmp_path / "mini", "Mac mini", carried)
    mac.repo.set_carry_secret(True)
    config: dict[str, object] = {
        "base_url": "https://gateway.example/v1",
        "secret_ref": "provider/p1/key",
    }
    document = resource("provider", "p1", "p" * 32, config)
    mac.put("resources/provider/p1.json", document)
    mac.put("secret/provider/p1/key.enc", _fernet(1000))
    join(mac.engine, carried, None)
    join(mini.engine, carried, None)

    assert mini.disk("resources/provider/p1.json") == document
    assert mini.disk("secret/provider/p1/key.enc") == _fernet(1000)
    assert b"gAAAA" not in document

    edited = resource(
        "provider", "p1", "p" * 32, {**config, "base_url": "https://other.example/v1"}
    )
    mac.put("resources/provider/p1.json", edited)
    mac.round()
    mini.round()
    assert mini.disk("resources/provider/p1.json") == edited
