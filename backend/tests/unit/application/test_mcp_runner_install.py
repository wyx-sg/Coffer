"""Missing-runner detection + allowlisted install (spec 001 amendment)."""

from __future__ import annotations

import pytest

from coffer.application.mcp import runner_install
from coffer.application.mcp.runner_install import (
    RunnerInstallFailed,
    RunnerInstallUnsupported,
    install_runner,
    missing_runner,
    runner_installable,
)


def test_missing_runner_detection(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # A resolvable command (sh is everywhere) is not missing.
    assert missing_runner("sh") is None
    # A bare name not on PATH reports its basename.
    assert missing_runner("definitely-not-a-real-runner-xyz") == "definitely-not-a-real-runner-xyz"
    # Absolute paths check existence directly.
    existing = tmp_path / "tool"
    existing.write_text("#!/bin/sh\n")
    assert missing_runner(str(existing)) is None
    assert missing_runner(str(tmp_path / "gone")) == "gone"
    assert missing_runner("") is None


def test_installable_allowlist() -> None:
    assert runner_installable("uvx") and runner_installable("npx") and runner_installable("bunx")
    assert not runner_installable("some-random-binary")


def test_install_unsupported_runner_rejects() -> None:
    with pytest.raises(RunnerInstallUnsupported):
        install_runner("some-random-binary")


def test_install_runs_the_allowlisted_formula(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[list[str]] = []

    class _Proc:
        returncode = 0
        stderr = ""

    def fake_run(argv, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(list(argv))
        return _Proc()

    monkeypatch.setattr(runner_install.shutil, "which", lambda _c: "/opt/homebrew/bin/brew")
    monkeypatch.setattr(runner_install.subprocess, "run", fake_run)
    assert install_runner("uvx") == "uv"
    assert calls == [["brew", "install", "uv"]]


def test_install_failure_surfaces_stderr(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class _Proc:
        returncode = 1
        stderr = "no bottle available"

    monkeypatch.setattr(runner_install.shutil, "which", lambda _c: "/opt/homebrew/bin/brew")
    monkeypatch.setattr(runner_install.subprocess, "run", lambda *a, **k: _Proc())
    with pytest.raises(RunnerInstallFailed, match="no bottle available"):
        install_runner("npx")
