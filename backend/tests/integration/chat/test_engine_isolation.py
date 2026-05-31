"""Engine isolation: LangChain/LangGraph live only in infrastructure (spec 008).

Belt-and-braces alongside importlinter Contract 7 — a fast static check that no
module under ``coffer.domain`` or ``coffer.application`` references the engine,
so a regression is caught even if the import-linter job is skipped. (SC-006)
"""

from __future__ import annotations

import pathlib
import re

import pytest

import coffer

_ENGINE = re.compile(r"\b(?:import|from)\s+(?:langgraph|langchain[\w]*)\b")
_ROOT = pathlib.Path(coffer.__file__).resolve().parent


def _modules(*subpackages: str) -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for sub in subpackages:
        files.extend((_ROOT / sub).rglob("*.py"))
    return files


@pytest.mark.acceptance(
    spec="008-builtin-agent-chat", scenario="built-in agent runtime is engine-isolated"
)
def test_engine_not_imported_in_domain_or_application():
    offenders = [
        str(p.relative_to(_ROOT))
        for p in _modules("domain", "application")
        if _ENGINE.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"engine imported outside infrastructure: {offenders}"


def test_engine_is_used_in_infrastructure():
    # Guard against the previous check passing vacuously: the engine MUST be
    # referenced somewhere in infrastructure (the built-in runtime).
    hits = [p for p in _modules("infrastructure") if _ENGINE.search(p.read_text(encoding="utf-8"))]
    assert hits, "expected the engine to be used in coffer.infrastructure"
