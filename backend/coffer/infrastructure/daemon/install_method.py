"""How the running Coffer was installed — the fact an upgrade depends on.

Read off the running process: a frozen build inside an ``.app`` bundle is the
desktop app, any other frozen build is the installer's (or a release
archive's) binaries, and an interpreter is a source run — in a checkout when
the package sits in one (its ``backend/`` beside a ``.git``).
"""

from __future__ import annotations

import sys
from pathlib import Path

import coffer
from coffer.application.upgrade_handoff import InstallFacts, InstallMethod


def _checkout_root() -> str | None:
    # coffer/__init__.py → coffer/ → backend/ → the checkout root.
    root = Path(coffer.__file__).resolve().parents[2]
    return str(root) if (root / ".git").exists() else None


def install_facts(*, frozen: bool | None = None, executable: str | None = None) -> InstallFacts:
    """This process's install method; the keywords are for tests."""
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    exe = executable if executable is not None else sys.executable
    if is_frozen:
        in_app = ".app/Contents/MacOS/" in exe
        return InstallFacts(
            method=InstallMethod.APP if in_app else InstallMethod.BINARIES, executable=exe
        )
    return InstallFacts(method=InstallMethod.SOURCE, executable=exe, checkout=_checkout_root())


__all__ = ["install_facts"]
