"""The OS-kept machine id: which source each host reads."""

from __future__ import annotations

import pathlib
from types import SimpleNamespace

from coffer.infrastructure.platform import identity


def test_linux_reads_the_first_readable_machine_id(tmp_path: pathlib.Path, monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    dbus = tmp_path / "dbus"
    dbus.write_text("abc123\n", encoding="utf-8")
    monkeypatch.setattr(identity, "LINUX_SOURCES", (str(tmp_path / "missing"), str(dbus)))
    assert identity.os_machine_id() == "abc123"


def test_macos_parses_ioreg(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    out = '  "IOPlatformSerialNumber" = "X"\n    "IOPlatformUUID" = "1E4C-AB"\n'
    monkeypatch.setattr(
        identity.subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(returncode=0, stdout=out),
    )
    assert identity.os_machine_id() == "1E4C-AB"


def test_macos_ioreg_failure_answers_none(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(
        identity.subprocess, "run", lambda *_a, **_k: SimpleNamespace(returncode=1, stdout="")
    )
    assert identity.os_machine_id() is None


def test_other_hosts_keep_no_id(monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    assert identity.os_machine_id() is None
