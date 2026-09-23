"""The engine's consumers reach it through ports (spec internal-engine).

Read from the source rather than from import-linter's report so the claim is
about exactly the consumers the requirement names: none of them imports the
provider kind's application package, directly or under ``TYPE_CHECKING``, and
the knowledge and memory consumers name ``ModelSelectorPort`` instead.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

_COFFER = pathlib.Path(__file__).resolve().parents[3] / "coffer"
_FORBIDDEN = "coffer.application.provider"

#: Every module the engine's consumers and the engine itself are written in.
_CONSUMERS = (
    "application/knowledge",
    "application/memory",
    "application/engine",
    "application/engine_ports.py",
    "application/engine_timeout.py",
    "infrastructure/sync/conflict_resolver.py",
    "infrastructure/llm/transcription.py",
)

#: The consumers that ask for the engine's connection through the selector port.
_SELECTOR_USERS = (
    "application/knowledge/ingest.py",
    "application/knowledge/curate.py",
    "application/memory/distil.py",
    "application/memory/service.py",
)


def _modules(rel: str) -> list[pathlib.Path]:
    path = _COFFER / rel
    return sorted(path.rglob("*.py")) if path.is_dir() else [path]


def _imports(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="consumers reach the engine without importing the provider kind",
)
def test_no_engine_consumer_imports_the_provider_kind() -> None:
    files = [f for rel in _CONSUMERS for f in _modules(rel)]
    assert len(files) >= len(_CONSUMERS)
    offenders = {
        str(f.relative_to(_COFFER)): sorted(
            n for n in _imports(f) if n == _FORBIDDEN or n.startswith(_FORBIDDEN + ".")
        )
        for f in files
    }
    assert {k: v for k, v in offenders.items() if v} == {}

    for rel in _SELECTOR_USERS:
        assert "coffer.application.engine_ports.ModelSelectorPort" in _imports(_COFFER / rel), rel
