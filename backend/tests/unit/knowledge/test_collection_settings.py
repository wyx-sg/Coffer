"""What a collection declares in its README, and the templates a new one
starts from (spec knowledge "Let each collection declare its own rules",
"Start a collection from a template").

The knowledge root resolves from the fresh ``HOME`` every test gets
(``backend/tests/conftest.py``), never the developer's real vault.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.application.knowledge import templates
from coffer.application.knowledge.guide_render import render_catalogue
from coffer.infrastructure.knowledge import catalogue, collection_settings, fs, paths
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter


def _collection(name: str, files: dict[str, str]) -> pathlib.Path:
    directory = fs.create_collection_dir(name)
    for relpath, text in files.items():
        path = directory / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return directory


def _entries() -> dict[str, object]:
    return {entry.name: entry for entry in catalogue.list_collections()}


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="a collection declares its rules file, its start page and its uploads folder",
)
def test_a_collection_declares_its_rules_entry_and_uploads() -> None:
    _collection(
        "shopee",
        {
            "README.md": "---\nrules: schema.md\nentry: index.md\nuploads: material\n---\n\n"
            "# shopee\n\nHow the shop is built.\n",
            "schema.md": "# Schema\n",
            "index.md": "# Index\n",
            "AGENTS.md": "# Not these\n",
            "pages/a.md": "# A\n",
            "pages/b.md": "# B\n",
        },
    )

    entry = _entries()["shopee"]

    assert (entry.rules_file, entry.entry_file, entry.uploads_dir) == (
        "schema.md",
        "index.md",
        "material",
    )
    assert entry.note_count == 5
    assert entry.description == "How the shop is built."
    assert paths.uploads_dir("shopee") == paths.collection_dir("shopee") / "material"


@pytest.mark.acceptance(
    spec="knowledge", scenario="a collection that declares nothing falls back to its root files"
)
def test_a_collection_that_declares_nothing_falls_back() -> None:
    _collection("plain", {"README.md": "# plain\n\nNotes.\n", "CLAUDE.md": "# Rules\n"})
    _collection("missing", {"README.md": "---\nrules: missing.md\n---\n\n# missing\n"})

    plain, missing = _entries()["plain"], _entries()["missing"]

    assert (plain.rules_file, plain.entry_file, plain.uploads_dir) == ("CLAUDE.md", "", "sources")
    assert missing.rules_file == "README.md"


@pytest.mark.parametrize(
    "uploads", ["../elsewhere", ".hidden", "/abs", "a/../../b", "", "README.md"]
)
def test_an_uploads_folder_outside_the_collection_keeps_the_default(uploads: str) -> None:
    directory = _collection("c", {"README.md": f"---\nuploads: {uploads!r}\n---\n\n# c\n"})
    assert collection_settings.read(directory).uploads == "sources"


def test_a_declared_file_may_not_leave_the_knowledge_root() -> None:
    directory = _collection("c", {"README.md": "---\nrules: ../../outside.md\n---\n# c\n"})
    (paths.knowledge_root().parent / "outside.md").write_text("x", encoding="utf-8")
    assert collection_settings.read(directory, bound=paths.knowledge_root()).rules == "README.md"


@pytest.mark.acceptance(spec="knowledge", scenario="collections share one rules file")
def test_collections_share_one_rules_file() -> None:
    _collection("shared", {"rules.md": "# House rules\n"})
    _collection(
        "team", {"README.md": "---\nrules: ../shared/rules.md\n---\n\n# team\n", "a.md": "# A\n"}
    )

    team = _entries()["team"]
    text = render_catalogue("~/k", [(team, catalogue.walk_files(paths.collection_dir("team")))])

    assert team.rules_file == "../shared/rules.md"
    assert "Its rules are in `../shared/rules.md`" in text


def test_the_description_is_the_first_paragraph_before_a_section() -> None:
    directory = _collection(
        "c",
        {
            "README.md": "---\nrules: AGENTS.md\n---\n\n# c\n\nFirst line\nwraps on.\n\n"
            "Second paragraph.\n\n## How\n\nNot this.\n"
        },
    )
    assert collection_settings.description(directory) == "First line wraps on."
    assert (
        collection_settings.description(_collection("bare", {"README.md": "# bare\n\n## x\n"}))
        == ""
    )


def test_the_llm_wiki_template_declares_its_rules_and_start_page() -> None:
    files = templates.render(templates.LLM_WIKI, "shopee", "How the shop is built.")

    assert sorted(files) == ["AGENTS.md", "README.md", "index.md"]
    fm, body = split_frontmatter(files["README.md"])
    assert fm == {"rules": "AGENTS.md", "entry": "index.md"}
    assert body.lstrip().startswith("# shopee\n\nHow the shop is built.\n")
    assert "{" not in files["README.md"]


def test_the_blank_template_is_a_readme_alone() -> None:
    files = templates.render(templates.BLANK, "notes", "My notes.")
    assert files == {"README.md": "# notes\n\nMy notes.\n"}
    assert templates.render(templates.LLM_WIKI, "x", None)["README.md"].count("\n\n\n") == 0
    with pytest.raises(ValueError):
        templates.render("nope", "x", None)
