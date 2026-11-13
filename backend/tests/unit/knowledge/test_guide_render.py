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
    display_root,
    render,
    render_catalogue,
    render_description,
)
from coffer.domain.knowledge.entry import CollectionEntry, FileEntry
from coffer.domain.skill.validator import ValidationOk, validate_skill_folder


def _collection(name: str, description: str, documents: int = 1):  # type: ignore[no-untyped-def]
    entry = CollectionEntry(
        uid=f"uid-{name}",
        name=name,
        description=description,
        note_count=documents,
        rules_file="AGENTS.md",
    )
    files = [
        FileEntry(
            path=f"{name}/pages/doc{i}.md",
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


@pytest.mark.acceptance(
    spec="knowledge", scenario="one skill carries both Coffer's manual and the catalogue"
)
def test_the_body_carries_both_halves() -> None:
    """One skill, two jobs: how Coffer works, and what it currently holds —
    the manual first, the catalogue after it, in one file."""
    text = render(
        "~/.coffer/knowledge",
        [_collection("shopee", "Shopee's account system.")],
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
    assert "read its rules file" in manual  # how an agent adds knowledge
    assert "### Tidying a collection" in manual
    assert "Everything left out is\nstill callable" in manual  # the tiering contract
    assert "Nothing here waits on a human" in manual
    assert "1 Markdown file: `pages/` 1." in catalogue
    assert "~/.coffer/knowledge/shopee/" in catalogue


@pytest.mark.acceptance(
    spec="knowledge", scenario="name one tool, the knowledge root and the log reader in the manual"
)
def test_the_manual_names_one_tool_and_the_log_reader() -> None:
    import re

    text = render("~/.coffer/knowledge", [_collection("ops", "Runbooks.")])
    named = set(re.findall(r"coffer__[a-z_]+", text))
    assert named == {"coffer__search_tools"}
    assert "coffer__write" not in text
    assert "coffer__recall" not in text
    assert "coffer__diagnose" not in text
    assert "adds one tool of its own" in text
    # Knowledge is written straight into a collection, tidied there, and never
    # committed through git in the vault.
    assert "Before you write in a collection, read its rules file" in text
    assert "Never run git inside the vault" in text
    # The only knowledge commands it names are the ones a tidy runs and the
    # one that imports a Confluence page: writing a page is a file edit, never
    # a command.
    commands = set(re.findall(r"coffer knowledge ([a-z-]+)", text))
    assert commands == {"tidy-start", "tidy-finish", "check", "upload"}
    assert "coffer path knowledge" not in text
    assert "coffer path memory" not in text
    assert "trigger" not in text
    # Memory reaches an agent through its own native memory: no root is named.
    assert "derived/memory" not in text
    assert "<MEMORY_ROOT>" not in text
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


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="the writing and tidying sections are absent while knowledge is off",
)
def test_with_knowledge_switched_off_the_manual_documents_no_knowledge_tool_or_root() -> None:
    """The whole guide, not only its description: the writing and tidying
    instructions and the knowledge root leave with the feature."""
    text = render("~/.coffer/knowledge", None)
    for heading in ("Tidying a collection", "Checking a collection"):
        assert f"### {heading}" not in text, heading
    assert "rules file" not in text
    assert "~/.coffer/knowledge" not in text
    assert "adds one tool of its own" in text
    assert "<!--" not in text


@pytest.mark.acceptance(
    spec="knowledge", scenario="the manual says where a skill's scripts keep their files"
)
def test_the_manual_says_where_a_skills_scripts_keep_their_files() -> None:
    for text in (
        render("~/.coffer/knowledge", [_collection("ops", "Runbooks.")]),
        render("~/.coffer/knowledge", None),
    ):
        assert "`~/.coffer/skill-data/<skill-name>/`" in text
        assert "`coffer path skill-data`" in text
        flat = " ".join(text.split())
        assert "Never write them inside the skill's own folder" in flat
        assert "Skill working files retention window" in flat
        assert "durable data does not belong there" in flat


def test_with_every_feature_on_no_span_marker_reaches_an_agent() -> None:
    text = render("~/.coffer/knowledge", [_collection("ops", "Runbooks.")])
    assert "<!--" not in text
    assert "<MEMORY_ROOT>" not in text
    assert "adds one tool of its own" in text


def _section(text: str, heading: str) -> str:
    """The body of one ``### heading`` section, up to the next heading."""
    start = text.index(f"### {heading}")
    rest = text[start + len(heading) + 4 :]
    end = min((i for i in (rest.find("\n## "), rest.find("\n### ")) if i != -1), default=len(rest))
    return rest[:end]


@pytest.mark.acceptance(
    spec="knowledge", scenario="the rendered guide carries the writing and tidying sections"
)
def test_the_guide_carries_the_writing_and_tidying_sections() -> None:
    text = render("~/.coffer/knowledge", [_collection("ops", "Runbooks.")])
    flat = " ".join(text.split())
    assert "Before you write in a collection, read its rules file" in flat
    assert "### Tidying a collection" in text
    # Checking is part of tidying, not a section of its own.
    assert "### Checking a collection" not in text
    description = yaml.safe_load(text.split("---", 2)[1])["description"].lower()
    assert "writ" in description and "tidy" in description and "check" in description


@pytest.mark.acceptance(spec="knowledge", scenario="the guide sets no format of its own")
def test_the_guide_sets_no_format_of_its_own() -> None:
    text = render("~/.coffer/knowledge", [_collection("ops", "Runbooks.")])
    # The manual, not the catalogue, which names the folders a collection has.
    manual = text[: text.index("## What is in this developer's knowledge")]
    flat = " ".join(manual.split())
    assert "Coffer sets no format for it" in flat
    assert "It wins over anything you would do by default" in flat
    assert "broken link" in flat
    assert "uploads folder" in flat
    # No page type, no required key, no folder a collection must have.
    for word in ("`pages/`", "`type`", "`verified`", "`sources` key", "overview", "how-to"):
        assert word not in flat, word
    assert "### Writing a page" not in text
    assert "### Integrating sources" not in text


def _file(path: str, title: str, description: str = ""):  # type: ignore[no-untyped-def]
    return FileEntry(
        path=path,
        title=title,
        description=description or f"What {title} answers.",
        actor="agent",
        updated_at="",
    )


@pytest.mark.acceptance(
    spec="knowledge", scenario="the skill body carries the catalogue and the absolute root"
)
def test_the_catalogue_counts_files_by_top_folder_with_the_rules_file() -> None:
    entry = CollectionEntry(
        uid="u", name="shopee", description="Accounts.", note_count=4, rules_file="AGENTS.md"
    )
    files = [
        _file("shopee/AGENTS.md", "Rules for this collection"),
        _file("shopee/pages/sessions.md", "Sessions"),
        _file("shopee/pages/login/otp.md", "OTP"),
        _file("shopee/sources/design.md", "Design doc"),
    ]
    text = render_catalogue("~/.coffer/vault/knowledge", [(entry, files)])

    assert "Its rules are in `AGENTS.md`" in text
    assert "4 Markdown files: `pages/` 2, `sources/` 1, 1 at the root." in text
    assert "search the folder for what you need" in text
    assert "`~/.coffer/vault/knowledge/shopee/`" in text
    # No file is listed by name, title or description.
    for absent in ("sessions.md", "Sessions", "What Sessions answers.", "login"):
        assert absent not in text, absent


@pytest.mark.acceptance(
    spec="knowledge", scenario="a collection with a start page is listed by its start page"
)
def test_a_collection_with_a_start_page_is_listed_by_its_count() -> None:
    entry = CollectionEntry(
        uid="u",
        name="shopee",
        description="",
        note_count=12,
        rules_file="schema.md",
        entry_file="index.md",
    )
    files = [_file(f"shopee/pages/p{i}.md", f"Page {i}") for i in range(12)]
    text = render_catalogue("~/k", [(entry, files)])

    assert "Its rules are in `schema.md`" in text
    assert "Start reading at `index.md`." in text
    assert "12 Markdown files." in text
    assert "p3.md" not in text and "Page 3" not in text


def test_a_collection_with_no_rules_file_is_written_like_its_files() -> None:
    entry = CollectionEntry(uid="u", name="bare", description="", note_count=1)
    text = render_catalogue("~/k", [(entry, [_file("bare/a.md", "A")])])
    assert "write in it the way its existing files are written" in text


@pytest.mark.acceptance(
    spec="knowledge", scenario="the catalogue grows with a collection's folders, not its files"
)
def test_the_catalogue_is_as_long_for_two_thousand_files_as_for_two() -> None:
    entry = CollectionEntry(uid="u", name="big", description="", note_count=2)
    few = [_file(f"big/pages/p{i}.md", f"Page {i}") for i in range(2)]
    many = [_file(f"big/pages/p{i}.md", f"Page {i}", "x" * 200) for i in range(2000)]

    small = render_catalogue("~/k", [(entry, few)])
    large = render_catalogue("~/k", [(entry, many)])

    assert "2000 Markdown files: `pages/` 2000." in large
    assert "p7.md" not in large and "Page 7" not in large
    assert len(large) - len(small) == len("2000") * 2 - len("2") * 2


@pytest.mark.acceptance(
    spec="knowledge", scenario="the guide lists a linked folder with its own path and rules"
)
def test_the_guide_lists_a_linked_folder_with_its_own_path_and_rules() -> None:
    home = pathlib.Path.home()
    entry = CollectionEntry(
        uid="uid-work",
        name="Work",
        description="My work notes.",
        folder_path=str(home / "Obsidian" / "Work"),
        linked=True,
        note_count=1,
        rules_file="AGENTS.md",
    )
    note = FileEntry(
        path="Work/Projects/Gateway.md",
        title="Payment gateway",
        description="",
        actor="user",
        updated_at="",
    )
    text = render("~/.coffer/vault/knowledge", [_collection("shopee", "Shopee."), (entry, [note])])

    assert "### Work (linked folder)" in text
    assert "`~/Obsidian/Work/`" in text
    assert "Its rules are in `AGENTS.md`" in text
    assert "1 Markdown file: `Projects/` 1." in text
    assert "Gateway.md" not in text
    assert str(home) not in text
    assert "Work (My work notes)" in render_description([(entry, [note])])


def test_a_chinese_readme_contributes_only_its_first_sentence() -> None:
    """A README written in Chinese ends its sentences with a full-width stop;
    the whole paragraph must not ride into the skill's description."""
    catalogue = [_collection("payments", "支付系统的知识。包括对账、退款和各种坑。")]
    description = render_description(catalogue)
    assert "payments (支付系统的知识)" in description
    assert "对账" not in description
