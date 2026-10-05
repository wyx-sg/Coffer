"""The boundary's machine-local files are sealed: an edit by anything but the
daemon does not change what it honours (spec secret; threat = a same-user process
with file access that cannot read the master key)."""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator
from typing import Any

import pytest

from coffer.domain.secret_errors import SecretBindingPending
from coffer.domain.secrets import SecretBinding
from coffer.infrastructure.secret.boundary_store import FileBoundaryStore
from coffer.infrastructure.vault.home import local_root
from tests.support.boundary_daemon import BoundaryDaemon, prepare_home, running_daemon

KEY = b"k" * 32


def _store(home: pathlib.Path, *, development: bool, key: bytes | None = KEY) -> FileBoundaryStore:
    return FileBoundaryStore(home, seal_key=lambda: key, development=development)


def _file(home: pathlib.Path, name: str) -> pathlib.Path:
    return local_root(home) / "secret-boundary" / name


def _edit(path: pathlib.Path, change: Any) -> None:
    doc = json.loads(path.read_text())
    change(doc)
    path.write_text(json.dumps(doc))


def _binding(uid: str = "u1") -> SecretBinding:
    return SecretBinding(
        ref="gh/token",
        destination_kind="mcp_server",
        destination_uid=uid,
        slot="TOKEN",
        target_fingerprint="fp",
        approved_at="2026-01-01T00:00:00Z",
        approval_id=None,
    )


@pytest.mark.parametrize("development", [True, False])
def test_round_trip_keeps_state_and_seals(tmp_path: pathlib.Path, development: bool) -> None:
    s = _store(tmp_path, development=development)
    s.put_binding(_binding())
    s.set_setting("require_approval", "true")
    again = _store(tmp_path, development=development)
    assert again.has_any_binding("gh/token")
    assert again.get_setting("require_approval") == "true"
    assert "_seal" in json.loads(_file(tmp_path, "bindings.json").read_text())
    assert "_seal" in json.loads(_file(tmp_path, "settings.json").read_text())


def test_hand_edited_settings_is_ignored_when_signed(tmp_path: pathlib.Path) -> None:
    s = _store(tmp_path, development=False)
    s.set_setting("require_approval", "true")
    _edit(_file(tmp_path, "settings.json"), lambda d: d.update(require_approval="false"))
    assert s.get_setting("require_approval") is None


def test_hand_added_binding_is_not_honoured(tmp_path: pathlib.Path) -> None:
    s = _store(tmp_path, development=False)
    s.put_binding(_binding("u1"))
    row = json.loads(_file(tmp_path, "bindings.json").read_text())["bindings"][0]
    _edit(
        _file(tmp_path, "bindings.json"),
        lambda d: d["bindings"].append({**row, "destination_uid": "evil"}),
    )
    assert s.get_binding("gh/token", "mcp_server", "evil", "TOKEN") is None
    assert not s.has_any_binding("gh/token")
    s.put_binding(_binding("u2"))  # the next write reseals, dropping the edit
    assert [b.destination_uid for b in s.bindings()] == ["u2"]


def test_unsealed_file_is_untrusted_when_signed(tmp_path: pathlib.Path) -> None:
    path = _file(tmp_path, "settings.json")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"require_approval": "false"}))
    assert _store(tmp_path, development=False).get_setting("require_approval") is None


def test_development_adopts_unsealed_legacy_and_seals_on_write(tmp_path: pathlib.Path) -> None:
    path = _file(tmp_path, "settings.json")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"require_approval": "true"}))
    s = _store(tmp_path, development=True)
    assert s.get_setting("require_approval") == "true"
    s.set_setting("other", "1")
    assert "_seal" in json.loads(path.read_text())
    assert s.get_setting("require_approval") == "true"
    assert _store(tmp_path, development=False).get_setting("require_approval") == "true"


@pytest.mark.parametrize("development", [True, False])
def test_forged_seal_is_rejected(tmp_path: pathlib.Path, development: bool) -> None:
    s = _store(tmp_path, development=development)
    s.set_setting("require_approval", "true")
    _edit(
        _file(tmp_path, "settings.json"),
        lambda d: d.update(_seal="0" * 64, require_approval="false"),
    )
    assert s.get_setting("require_approval") is None
    # a seal under another key is no better
    other = _store(tmp_path, development=development, key=b"z" * 32)
    other.set_setting("require_approval", "true")
    assert s.get_setting("require_approval") is None


def test_without_a_key_nothing_is_sealed(tmp_path: pathlib.Path) -> None:
    s = _store(tmp_path, development=False, key=None)
    s.set_setting("require_approval", "true")
    assert "_seal" not in json.loads(_file(tmp_path, "settings.json").read_text())
    assert s.get_setting("require_approval") == "true"


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as d:
        yield d


def test_daemon_ignores_hand_edited_boundary_files(daemon: BoundaryDaemon) -> None:
    d = daemon
    d.store("gh/token", "ghp_seal_value_1")
    first = d.register_stdio("first", "server-one", {"TOKEN": "gh/token"})
    assert d.resolve_for(first) == {"TOKEN": "ghp_seal_value_1"}
    second = d.register_stdio("second", "evil.sh", {"TOKEN": "gh/token"})
    with pytest.raises(SecretBindingPending):
        d.resolve_for(second)

    # An outside edit to the approved bindings (here: re-pointing the approved
    # row at the second server) carries a wrong seal, so the daemon drops the
    # file: the first server is no longer approved and the second is not either
    # (this development build would adopt an unsealed file, never a forged seal).
    def repoint(doc: dict[str, Any]) -> None:
        for row in doc["bindings"]:
            row["destination_uid"] = second["uid"]

    _edit(_file(d.home, "bindings.json"), repoint)
    with pytest.raises(SecretBindingPending):
        d.resolve_for(second)
    with pytest.raises(SecretBindingPending):
        d.resolve_for(first)
