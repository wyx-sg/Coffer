"""The knowledge layer carries no vector store and fences its one converter."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

PYPROJECT = Path(__file__).resolve().parents[3] / "pyproject.toml"
VECTOR_PACKAGES = ("sqlite-vec", "fastembed", "mem0", "chroma", "llama-index")
MARKITDOWN_IMPORTERS = {
    "coffer.infrastructure.chat.document_extract -> markitdown",
    "coffer.infrastructure.knowledge.converters.markitdown_converter -> markitdown",
}


def _declared(config: dict) -> list[str]:
    project = config["project"]
    names = list(project["dependencies"])
    for extra in project.get("optional-dependencies", {}).values():
        names.extend(extra)
    return [re.split(r"[\[<>=!~;\s]", name, maxsplit=1)[0].lower() for name in names]


@pytest.mark.acceptance(spec="knowledge", scenario="the dependency set holds no vector store")
def test_no_vector_store_is_declared_and_markitdown_has_two_importers() -> None:
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))

    declared = _declared(config)
    for package in VECTOR_PACKAGES:
        assert not any(name.startswith(package) for name in declared), package

    fences = [
        contract
        for contract in config["tool"]["importlinter"]["contracts"]
        if "markitdown" in contract.get("forbidden_modules", [])
    ]
    assert len(fences) == 1
    fence = fences[0]
    # The whole package is fenced, so a new package cannot slip past it.
    assert fence["source_modules"] == ["coffer"]
    assert set(fence.get("ignore_imports", [])) == MARKITDOWN_IMPORTERS
