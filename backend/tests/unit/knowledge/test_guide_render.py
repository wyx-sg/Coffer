"""Rendering Coffer's own skill.

The two things worth pinning here are the two that fail silently: a description
that grows past the importers' cap, and a body that is not the same bytes on
two machines. Neither shows up as an error — the first is truncated by whoever
reads it, the second by two vaults quietly overwriting each other every round.
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest
import yaml

from coffer.application.knowledge.guide_render import (
    GUIDE_SKILL_NAME,
    MAX_DESCRIPTION_CHARS,
    display_memory_root,
    display_root,
    render,
    render_description,
)
from coffer.domain.knowledge.entry import CollectionEntry, FileEntry
from coffer.domain.skill.validator import ValidationOk, validate_skill_folder


def _collection(name: str, description: str, documents: int = 1):  # type: ignore[no-untyped-def]
    entry = CollectionEntry(
        uid=f"uid-{name}",
        name=name,
        description=description,
        document_count=documents,
    )
    files = [
        FileEntry(
            path=f"{name}/doc{i}.md",
            title=f"Doc {i}",
            description="What it answers.",
            actor="curation",
            updated_at=None,
        )
        for i in range(documents)
    ]
    return entry, files


def test_the_default_root_is_rendered_home_relative() -> None:
    """``~`` is not cosmetic: it is what makes the file identical on two
    machines whose home directories differ."""
    home = pathlib.Path("/Users/someone")
    assert display_root(home / ".coffer" / "knowledge", home=home) == "~/.coffer/knowledge"


def test_the_memory_root_follows_the_same_rule() -> None:
    home = pathlib.Path("/Users/someone")
    assert display_memory_root(home / ".coffer" / "memory", home=home) == "~/.coffer/memory"
    assert display_memory_root(pathlib.Path("/mnt/memory"), home=home) == "/mnt/memory"


def test_a_moved_root_is_rendered_absolute() -> None:
    """Once the root is somewhere else, ``~`` would be a lie, and an accurate
    path matters more than a stable one."""
    home = pathlib.Path("/Users/someone")
    assert display_root(pathlib.Path("/mnt/vault/knowledge"), home=home) == "/mnt/vault/knowledge"


@pytest.mark.acceptance(
    spec="knowledge", scenario="the rendered skill is byte-identical on two machines"
)
def test_two_machines_render_the_same_bytes() -> None:
    """The master folder and the skill row both converge, and each machine
    regenerates them at every boot. Anything machine-specific in here would
    leave two vaults overwriting each other forever, each one correct."""
    catalogue = [_collection("shopee", "Shopee's account system.")]
    one = pathlib.Path("/Users/ana")
    two = pathlib.Path("/home/bruno")
    assert render(display_root(one / ".coffer" / "knowledge", home=one), catalogue) == render(
        display_root(two / ".coffer" / "knowledge", home=two), catalogue
    )


def test_the_rendering_is_stable_across_calls() -> None:
    """No timestamp, no ordering that depends on a set's iteration."""
    catalogue = [_collection("a", "First."), _collection("b", "Second.")]
    assert render("~/.coffer/knowledge", catalogue) == render("~/.coffer/knowledge", catalogue)


def test_the_description_stays_inside_the_importers_cap() -> None:
    """1024 is the tightest ceiling in play. A description over it is cut by
    whoever reads it, mid-word, with no error anywhere."""
    catalogue = [
        _collection(f"collection{i}", "A " + "long " * 40 + "description.") for i in range(40)
    ]
    description = render_description(catalogue)
    assert len(description) <= MAX_DESCRIPTION_CHARS


def test_subjects_are_dropped_from_the_tail_not_cut_mid_sentence() -> None:
    """Truncating the text would leave a dangling clause; dropping whole
    subjects leaves a shorter description that still reads."""
    catalogue = [
        _collection(f"collection{i}", "A " + "long " * 40 + "description.") for i in range(40)
    ]
    description = render_description(catalogue)
    assert description.endswith(".")
    assert "collection0" in description
    assert "collection39" not in description


def test_an_empty_corpus_still_renders_a_usable_manual() -> None:
    """A vault with nothing filed yet still needs the half of this skill that
    explains the tools — that half is what a new user's agent reads first."""
    text = render("~/.coffer/knowledge", [])
    assert f"name: {GUIDE_SKILL_NAME}" in text
    assert "coffer__search_tools" in text
    assert "No collections have been created yet" in text


_MEMORY = "~/.coffer/memory"


@pytest.mark.acceptance(
    spec="knowledge", scenario="one skill carries both Coffer's manual and the catalogue"
)
def test_the_body_carries_both_halves() -> None:
    """One skill, two jobs: how Coffer works, and what it currently holds —
    the manual first, the catalogue after it, in one file."""
    text = render(
        "~/.coffer/knowledge",
        [_collection("shopee", "Shopee's account system.")],
        memory_root=_MEMORY,
    )
    _, frontmatter, body = text.split("---", 2)
    description = yaml.safe_load(frontmatter)["description"]
    assert len(description) <= MAX_DESCRIPTION_CHARS
    assert "Coffer" in description
    assert "coffer__search_tools" in description
    assert "coffer__write" not in description
    assert "shopee (Shopee's account system)" in description

    manual_end = body.index("## What is in this developer's knowledge")
    manual, catalogue = body[:manual_end], body[manual_end:]
    assert "`coffer__search_tools`" in manual
    assert "`coffer__write`" not in manual
    assert "/.inbox/" in manual  # how an agent adds knowledge
    assert "Everything left out is\nstill callable" in manual  # the tiering contract
    assert "never writes it" in manual
    assert "Nothing here waits on a human" in manual
    assert "`doc0.md` — **Doc 0**" in catalogue
    assert "~/.coffer/knowledge/shopee/" in catalogue


@pytest.mark.acceptance(
    spec="knowledge", scenario="name one tool, both roots and the log reader in the manual"
)
def test_the_manual_names_one_tool_the_memory_root_and_the_log_reader() -> None:
    import re

    text = render("~/.coffer/knowledge", [_collection("ops", "Runbooks.")], memory_root=_MEMORY)
    named = set(re.findall(r"coffer__[a-z_]+", text))
    assert named == {"coffer__search_tools"}
    assert "coffer__write" not in text
    assert "coffer__recall" not in text
    assert "coffer__diagnose" not in text
    assert "adds one tool of its own" in text
    # Knowledge is added by writing a file into a collection's inbox, edited in
    # place, and never through git in the vault.
    assert "/.inbox/" in text
    assert "Never run git inside the vault" in text
    assert "coffer knowledge" not in text
    assert "coffer path knowledge" not in text
    assert "coffer path memory" not in text
    assert "trigger" not in text
    # The memory root, with the instruction to search it with the agent's own tools.
    assert f"`{_MEMORY}/<partition>/notes/`" in text
    assert f"search `{_MEMORY}` with your own tools" in text
    # Coffer's own logs are read with ``coffer log`` and located with ``coffer path logs``.
    assert "`coffer log audit`" in text
    assert "`coffer log daemon`" in text
    assert "`coffer path logs`" in text
    # The command-line tools Coffer manages are read with ``coffer cli list``.
    assert "`coffer cli list`" in text


# --- the frontmatter is not ours to interpolate ------------------------------
#
# The description is built from the collections' own READMEs, so it carries
# whatever punctuation a person wrote. Every test above this line used prose
# with none — which is exactly how the defect these cover survived: the skill
# was rendered, failed validation, and was silently never written.


def _roundtrip(description: str) -> tuple[str, str]:
    """Render a one-collection catalogue and parse it back the way an importer
    would — through the real validator, not a regex.

    Returns ``(what we wrote, what came back)``.
    """
    catalogue = [_collection("ops", description)]
    folder = pathlib.Path(tempfile.mkdtemp()) / "coffer-guide"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(render("~/.coffer/knowledge", catalogue), encoding="utf-8")
    result = validate_skill_folder(folder)
    assert isinstance(result, ValidationOk), f"the skill did not even parse: {result}"
    return render_description(catalogue), result.frontmatter.description


@pytest.mark.parametrize(
    "description",
    [
        # The shape every README on this machine actually has.
        "Shopee-internal knowledge: the account system's services and data plane.",
        # Starts a YAML comment: parses, and silently eats the rest.
        "Runbooks # and the alerts that reference them.",
        "A quoted 'phrase' and a \"double-quoted\" one.",
        "Trailing colon: ",
        "- leading dash, which YAML reads as a sequence",
        "{braces} and [brackets] and a | pipe and a > angle",
        # A full-width colon: not a YAML indicator, but a reminder that the
        # corpus is not all ASCII and the dumper has to keep it verbatim.
        "中文的说明：账号系统的服务与数据面。",  # noqa: RUF001
        "A backslash \\ and a tab\tcharacter",
    ],
)
def test_a_readme_survives_the_frontmatter_intact(description: str) -> None:
    """What we wrote must be exactly what an importer reads back.

    Not merely "the block still parses": a ` #` parses perfectly and throws
    away everything after it, so equality is the only check that catches it.
    """
    written, parsed = _roundtrip(description)
    assert parsed == written


def test_the_parsed_description_is_what_the_cap_measures() -> None:
    """The 1024-char ceiling belongs to the value an importer reads, not to the
    quoted bytes on disk — quoting inflates the line and must not eat budget."""
    catalogue = [_collection("ops", "A " + "long " * 40 + "description.") for _ in range(40)]
    assert len(render_description(catalogue)) <= MAX_DESCRIPTION_CHARS


def test_with_knowledge_switched_off_the_guide_carries_no_catalogue() -> None:
    """``None`` is the knowledge feature switched off (spec
    experimental-features): the manual stays, the catalogue and every
    collection subject go, and the description promises no knowledge."""
    text = render("~/.coffer/knowledge", None)
    assert f"name: {GUIDE_SKILL_NAME}" in text
    assert "coffer__search_tools" in text
    assert "## What is in this developer's knowledge" not in text
    assert "No collections have been created yet" not in text
    description = text.split("---")[1]
    assert "knowledge" not in description
    assert "coffer__write" not in description
    assert render("~/.coffer/knowledge", None) == text


def test_with_knowledge_switched_off_the_manual_documents_no_knowledge_tool_or_root() -> None:
    """The whole guide, not only its description: the inbox instructions and the
    knowledge root leave with the feature."""
    text = render("~/.coffer/knowledge", None, memory_root=_MEMORY)
    assert "/.inbox/" not in text
    assert "~/.coffer/knowledge" not in text
    assert _MEMORY in text
    assert "adds one tool of its own" in text
    assert "<!--" not in text


def test_with_memory_switched_off_the_guide_names_no_memory_root() -> None:
    catalogue = [_collection("ops", "Runbooks.")]
    text = render("~/.coffer/knowledge", catalogue)
    assert "<MEMORY_ROOT>" not in text
    assert "~/.coffer/memory" not in text
    assert "## Coffer reads your memory" not in text
    assert "/.inbox/" in text
    assert "### ops" in text
    assert "adds one tool of its own" in text
    assert "memory notes" not in text.split("---")[1]

    both_off = render("~/.coffer/knowledge", None)
    assert "~/.coffer/memory" not in both_off
    assert "/.inbox/" not in both_off
    assert "adds one tool of its own" in both_off
    assert "`coffer path logs`" in both_off  # the log readers are always there
    assert "<!--" not in both_off


@pytest.mark.acceptance(
    spec="knowledge", scenario="the manual says where a skill's scripts keep their files"
)
def test_the_manual_says_where_a_skills_scripts_keep_their_files() -> None:
    for text in (
        render("~/.coffer/knowledge", [_collection("ops", "Runbooks.")], memory_root=_MEMORY),
        render("~/.coffer/knowledge", None),
    ):
        assert "`~/.coffer/skill-data/<skill-name>/`" in text
        assert "`coffer path skill-data`" in text
        flat = " ".join(text.split())
        assert "Never write them inside the skill's own folder" in flat
        assert "Skill working files retention window" in flat
        assert "durable data does not belong there" in flat


def test_with_every_feature_on_no_span_marker_reaches_an_agent() -> None:
    text = render("~/.coffer/knowledge", [_collection("ops", "Runbooks.")], memory_root=_MEMORY)
    assert "<!--" not in text
    assert "<MEMORY_ROOT>" not in text
    assert "adds one tool of its own" in text
    assert "memory notes" in text.split("---")[1]
