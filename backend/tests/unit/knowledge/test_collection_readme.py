"""A new collection's README carries its rules written out, and its description
is only the paragraph before them (spec knowledge "Start a collection's README
with its rules written out", "Read a collection's description from its README").
"""

from __future__ import annotations

import pytest

from coffer.infrastructure.knowledge import catalogue, collection_files, fs, paths, wiki


@pytest.mark.acceptance(spec="knowledge", scenario="a new collection's README lists its rules")
def test_a_new_collections_readme_lists_its_rules() -> None:
    fs.create_collection_dir("shopee")
    paths.readme_path("shopee").write_text(
        collection_files.default_readme("shopee", "How the shop is built."), encoding="utf-8"
    )
    text = paths.readme_path("shopee").read_text(encoding="utf-8")

    assert text.startswith("---\nverify_after_days: 90\n---\n\n# shopee\n\nHow the shop is built.")
    for page_type in ("overview", "concept", "entity", "how-to", "decision"):
        assert f"- `{page_type}`:" in text
    assert catalogue.readme_description("shopee") == "How the shop is built."
    assert wiki.verify_days("shopee") == 90


def test_without_a_description_the_rules_are_not_one() -> None:
    fs.create_collection_dir("notes")
    paths.readme_path("notes").write_text(
        collection_files.default_readme("notes", None), encoding="utf-8"
    )
    assert catalogue.readme_description("notes") == ""

    collection_files.write_description("notes", "My notes.")

    text = paths.readme_path("notes").read_text(encoding="utf-8")
    assert catalogue.readme_description("notes") == "My notes."
    assert text.index("My notes.") < text.index("## Page types")
    assert text.startswith("---\nverify_after_days: 90\n---")

    collection_files.write_description("notes", "Work notes.")
    text = paths.readme_path("notes").read_text(encoding="utf-8")
    assert "My notes." not in text and text.count("## Page types") == 1
