"""Migration 0066's on-disk rewrite is frozen: it must not track live code.

A migration describes one moment in the schema's history. The rewrite it runs
therefore lives next to the migration and carries its own copies of the
helpers it needs — importing the knowledge layer's live ``paths`` /
``naming`` / ``frontmatter`` would let a later product change silently alter
what an old upgrade does to a user's vault.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from coffer.infrastructure.persistence.migrations import (
    knowledge_tree_0066,
    knowledge_tree_0066_text,
)

_FROZEN_MODULES = (knowledge_tree_0066, knowledge_tree_0066_text)
_OWN_PACKAGE = "coffer.infrastructure.persistence.migrations."


def _imported_modules(module: object) -> set[str]:
    source = pathlib.Path(str(module.__file__)).read_text(encoding="utf-8")
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    return names


@pytest.mark.parametrize("module", _FROZEN_MODULES, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_frozen_rewrite_imports_nothing_live_from_coffer(module: object) -> None:
    coffer_imports = {
        name for name in _imported_modules(module) if name == "coffer" or name.startswith("coffer.")
    }
    outside_own_package = {name for name in coffer_imports if not name.startswith(_OWN_PACKAGE)}
    assert outside_own_package == set()


def test_root_comes_from_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "vault"))
    monkeypatch.setenv("HOME", str(tmp_path / "elsewhere"))
    assert knowledge_tree_0066_text.knowledge_root() == tmp_path / "vault"


def test_root_falls_back_to_home(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    monkeypatch.delenv("COFFER_KNOWLEDGE_ROOT", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert knowledge_tree_0066_text.knowledge_root() == tmp_path / ".coffer" / "knowledge"


def test_collection_for_maps_scopes_the_way_0066_shipped() -> None:
    assert knowledge_tree_0066.collection_for("global") == "shopee"
    assert knowledge_tree_0066.collection_for("project-01ABC") == "coffer"
    assert knowledge_tree_0066.collection_for("My Team Notes") == "my-team-notes"
