"""Tests for scripts/check_file_sizes.py — the file-size gate's exclusions.

The gate caps how long a source file may get, and it excludes generated files
(which are legitimately enormous and nobody edits). That exclusion is decided
from the file itself, which makes it the gate's one bypass: anything that can
claim the generated marker escapes the cap entirely. So the exclusion has to be
narrow enough that a hand-written module cannot claim it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from .conftest import REPO_ROOT

_SCRIPT = REPO_ROOT / "scripts" / "check_file_sizes.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_file_sizes", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_only_generated_typescript_can_claim_the_generated_exclusion() -> None:
    """A hand-written `.py` cannot escape the size cap.

    The generated marker is a comment, so any file can contain it. Eligibility
    is therefore gated on the extension as well: only `.ts`/`.tsx` (the API
    client the codegen emits) can be excluded, and a backend `.py` claiming the
    same marker is still measured.
    """
    mod = _load()
    assert mod._is_generated(Path("evil.py")) is False


def test_a_test_shaped_name_does_not_exclude_a_production_module() -> None:
    """`.test.` appearing inside a production filename must not match the
    test-file exclusion — otherwise `foo.test.helper.py` under `coffer/` is
    uncapped while being ordinary production code."""
    mod = _load()
    assert mod.is_excluded(Path("backend/coffer/foo.test.helper.py")) is False
