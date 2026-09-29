"""The privileged-path rules per host."""

from __future__ import annotations

import os

from coffer.infrastructure.platform import paths


def test_macos_rules_are_posix_with_the_private_firmlink(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    rules = paths.privileged_paths()
    assert rules.prefixes == paths.PRIVILEGED_PREFIXES_POSIX
    assert rules.carve_outs == ("/var/folders/",)
    assert rules.separator == os.sep
    assert rules.firmlink_root == "/private"


def test_linux_rules_are_posix_without_a_firmlink(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    rules = paths.privileged_paths()
    assert rules.prefixes == paths.PRIVILEGED_PREFIXES_POSIX
    assert rules.carve_outs == paths.PRIVILEGED_CARVE_OUTS_POSIX
    assert rules.firmlink_root is None


def test_windows_rules_use_backslash_and_no_carve_outs(monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    rules = paths.privileged_paths()
    assert rules.prefixes == paths.PRIVILEGED_PREFIXES_WIN
    assert rules.carve_outs == ()
    assert rules.separator == "\\"
    assert rules.firmlink_root is None
