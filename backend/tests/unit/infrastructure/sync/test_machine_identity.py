"""Where this machine's id comes from (spec vault-sync "Derive machine identity
from the host" and "Fall back to a stored identifier and say so").

The host is simulated rather than read: ``platform.system`` and the Linux
identifier paths are pointed at files under ``tmp_path``, and ``HOME`` is
``tmp_path`` too, so ``daemon-config.json`` and the fallback file land there
and never in the developer's real ``~/.coffer``.
"""

from __future__ import annotations

import pathlib
import stat

import pytest

from coffer.domain.sync.machine import derive_machine_id
from coffer.infrastructure.daemon.config import config_path, read_cached_machine_id
from coffer.infrastructure.sync import machine_id as machine_id_mod
from coffer.infrastructure.sync.identity import resolve_identity


@pytest.fixture
def home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _linux_host(monkeypatch: pytest.MonkeyPatch, *sources: pathlib.Path) -> None:
    monkeypatch.setattr(machine_id_mod.platform, "system", lambda: "Linux")
    monkeypatch.setattr(machine_id_mod, "_LINUX_SOURCES", tuple(str(s) for s in sources))


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a machine id is derived from the host and cached"
)
def test_the_id_comes_from_the_host_and_survives_losing_its_cache(
    home: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    etc = home / "etc-machine-id"  # never created: unreadable
    dbus = home / "dbus-machine-id"
    dbus.write_text("4c4c4544004d3510804ab4c04f4d3432\n", encoding="utf-8")
    _linux_host(monkeypatch, etc, dbus)
    coffer = home / ".coffer"
    expected = derive_machine_id("4c4c4544004d3510804ab4c04f4d3432")

    first = resolve_identity(coffer)

    assert first.machine_id == expected
    assert first.derived is True
    # Cached in daemon-config.json, under this test's HOME.
    assert config_path() == coffer / "daemon-config.json"
    assert read_cached_machine_id() == expected

    # The cache is lost; the host still answers the same.
    config_path().unlink()
    assert read_cached_machine_id() is None

    second = resolve_identity(coffer)

    assert second.machine_id == expected
    assert second.derived is True
    assert read_cached_machine_id() == expected
    # The host answered, so no locally-generated identifier was made.
    assert not (coffer / "machine-id").exists()


def test_etc_machine_id_is_preferred_to_the_dbus_copy(
    home: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    etc = home / "etc-machine-id"
    dbus = home / "dbus-machine-id"
    etc.write_text("from-etc\n", encoding="utf-8")
    dbus.write_text("from-dbus\n", encoding="utf-8")
    _linux_host(monkeypatch, etc, dbus)

    assert machine_id_mod.resolve(home / ".coffer").machine_id == derive_machine_id("from-etc")


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a machine with no host identifier falls back and says so"
)
def test_a_host_with_no_identifier_falls_back_to_a_private_stored_one(
    home: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _linux_host(monkeypatch, home / "no-etc", home / "no-dbus")
    coffer = home / ".coffer"

    first = machine_id_mod.resolve(coffer)
    second = machine_id_mod.resolve(coffer)

    stored = coffer / "machine-id"
    assert stored.is_file()
    assert stat.S_IMODE(stored.stat().st_mode) == 0o600
    raw = stored.read_text(encoding="utf-8").strip()
    assert first.machine_id == second.machine_id == derive_machine_id(raw)
    assert first.derived is False
    assert second.derived is False

    # Through the cached path too: the daemon still knows the id is not the host's.
    resolved = resolve_identity(coffer)
    again = resolve_identity(coffer)
    assert resolved.machine_id == again.machine_id == first.machine_id
    assert resolved.derived is False
    assert again.derived is False
